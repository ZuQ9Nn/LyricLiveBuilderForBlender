# Entrances ported from JIZURA (src/05_anim.js J.ENTER, src/11p_enter.js, src/11p_enterB.js, src/11p_horror*.js),
# MIT License, Copyright (c) 2026 hakoniwa. Rewritten for 3D text in VR.
"""Entrances added from JIZURA v0.10 (spec §7.4, design §5.6).

JIZURA computes every glyph's progress q from the whole entrance's p (stg / ordLR / ordC), so these parts start
all glyphs together (stagger 0) and use the same formulas. Units: JIZURA's dx / dy are in em here (y down
becomes -z), rot in degrees (clockwise, our roll). Nothing moves toward the viewer (-y); flips turn the glyph for
real. Blur becomes a fade with a little growth, skew an in-plane turn; 2D decorations (strings, balls, rays) are
left out. Parts that cut glyphs use the mask (design §5.6): 5 iris, 6 diagonal, 7 blinds, 8 shutter, 9 window."""
import math

import numpy as np

from .. import xform
from ..registry import Delta, MotionPart, register
from ..rng import h_np, noise1_np
from .common import clip, in_cubic, in_out_sine, out_back, out_cubic, out_expo

DEG = math.pi / 180
TAU = 2 * math.pi


# ---------------- helpers (JIZURA's names) ----------------

def stg(p, k, spread):
    return clip((p - spread * k) / (1 - spread))


def o_quart(x):
    return 1 - (1 - clip(x)) ** 4


def o_quint(x):
    return 1 - (1 - clip(x)) ** 5


def o_cubic(x):
    return 1 - (1 - clip(x)) ** 3


def o_back(x, s):
    return out_back(clip(x), s)


def io_quart(x):
    x = clip(x)
    return np.where(x < 0.5, 8 * x ** 4, 1 - (-2 * x + 2) ** 4 / 2)


def io_cubic(x):
    x = clip(x)
    return np.where(x < 0.5, 4 * x ** 3, 1 - (-2 * x + 2) ** 3 / 2)


def spring(t, k, f):
    t = clip(t)
    return np.exp(-k * t) * np.cos(f * np.pi * t) * (1 - t ** 3)


def smooth(a, b, x):
    x = clip((x - a) / (b - a))
    return x * x * (3 - 2 * x)


def bounce(x):
    """JIZURA's E.outBounce-like landing (src/05_anim.js bounce)."""
    x = clip(x)
    n1, d1 = 7.5625, 2.75
    return np.where(x < 1 / d1, n1 * x * x,
                    np.where(x < 2 / d1, n1 * (x - 1.5 / d1) ** 2 + 0.75,
                             np.where(x < 2.5 / d1, n1 * (x - 2.25 / d1) ** 2 + 0.9375, n1 * (x - 2.625 / d1) ** 2 + 0.984375)))


def _r(*k):
    return h_np(*k) / 4294967296.0


def _rs(*k):
    return _r(*k) * 2 - 1


def gi(ctx):
    return np.arange(ctx.n)[:, None].astype(float)


def ord_lr(ctx):
    return gi(ctx) / (ctx.n - 1) if ctx.n > 1 else np.zeros((ctx.n, 1))


def ord_rl(ctx):
    return 1 - ord_lr(ctx) if ctx.n > 1 else np.zeros((ctx.n, 1))


def ord_c(ctx):
    if ctx.n <= 1:
        return np.zeros((ctx.n, 1))
    half = (ctx.n - 1) / 2
    return np.abs(gi(ctx) - half) / half


def centred(ctx):
    """(G, 1) x and z of each glyph from the line's centre, in em (index spacing when there is no layout)."""
    rest = np.asarray(ctx.rest, dtype=np.float64)
    if len(rest) and np.any(rest.max(axis=0) - rest.min(axis=0)):
        c = (rest.max(axis=0) + rest.min(axis=0)) / 2
        return ((rest[:, 0] - c[0]) / ctx.em)[:, None], ((rest[:, 2] - c[2]) / ctx.em)[:, None]
    return gi(ctx) - (ctx.n - 1) / 2, np.zeros((ctx.n, 1))


def side(ctx, salt):
    """JIZURA's dirOf: -1 or 1 for the line."""
    return -1.0 if _r(ctx.seed, salt, 5) < 0.5 else 1.0


def out(ctx, p, dx=0.0, dy=0.0, rot=0.0, sx=1.0, sy=1.0, s=1.0, a=1.0, yaw=0.0, pitch=0.0,
        hide=False, live=True, mask=None, back=0.0):
    """A Delta from JIZURA-style values (dx, dy in em, dy down; angles in degrees; back: away from the
    viewer in em, never toward). hide: invisible; live False: the rest pose (JIZURA returns null)."""
    g, t = p.shape
    b = lambda v: np.broadcast_to(np.asarray(v, dtype=np.float64), (g, t))
    live = b(live).astype(bool)
    keep = lambda v, rest: np.where(live, b(v), rest)
    loc = np.zeros((g, t, 3))
    loc[..., 0] = keep(dx, 0.0) * ctx.em
    loc[..., 2] = -keep(dy, 0.0) * ctx.em
    loc[..., 1] = np.maximum(keep(back, 0.0), 0.0) * ctx.em
    rot = xform.mul(xform.roll(keep(rot, 0.0) * DEG),
                    xform.mul(xform.yaw(keep(yaw, 0.0) * DEG), xform.pitch(keep(pitch, 0.0) * DEG)))
    ss = keep(s, 1.0)
    scale = np.stack([keep(sx, 1.0) * ss, ss, keep(sy, 1.0) * ss], axis=-1)
    alpha = keep(a, 1.0) * (1 - b(hide))
    m = None if mask is None else np.where(live, b(mask), 1.0)
    return Delta(g, t, loc=loc, rot=rot, scale=scale, alpha=alpha, mask=m)


class _Enter(MotionPart):
    group = "extra"
    stagger = 0.0
    duration = 0.6


def part(key, name, tags, weight=1.0, duration=0.6, group="extra"):
    def deco(fn):
        cls = type(key, (_Enter,), {"name": name, "tags": tuple(tags), "weight": weight, "duration": duration,
                                    "group": group, "evaluate": lambda self, ctx, p: fn(ctx, p)})
        register("enter", key)(cls)
        return cls
    return deco


def whole(ctx, p, s=1.0, dx=0.0, dy=0.0, rot=0.0, a=1.0, sx=None, sy=None):
    """The whole line scaled (and turned) about its centre, then moved: per-glyph offsets."""
    cx, cz = centred(ctx)
    sx = s if sx is None else sx
    sy = s if sy is None else sy
    r = np.asarray(rot, dtype=np.float64) * DEG
    c, sn = np.cos(r), np.sin(r)
    x, z = cx * sx, cz * sy
    nx, nz = c * x + sn * z, -sn * x + c * z                   # clockwise in view = our roll
    return out(ctx, p, dx=nx - cx + dx, dy=-(nz - cz) + dy, rot=rot, sx=sx, sy=sy, a=a)


# ---------------- basic set ----------------

@part("cut", "Cut In", (), 1.0, 0.12, group="basic")
def cut(ctx, p):
    return out(ctx, p, hide=p <= 0)


@part("pop", "Pop", ("pop",), group="basic")
def pop(ctx, p):
    d = ord_lr(ctx) * 0.45
    q = clip((p - d) / 0.55)
    return out(ctx, p, s=o_back(q, 2.6), rot=(1 - o_cubic(q)) * _rs(ctx.seed, gi(ctx), 9) * 28, hide=q <= 0, live=q < 1)


@part("stretch", "Stretch In", ("glitch", "pop", "graphic"), group="basic")
def stretch(ctx, p):
    e = out_expo(p)
    return whole(ctx, p, sx=4.2 + (1 - 4.2) * e, sy=1.0)


@part("blur", "Blur In", ("calm", "editorial", "emotional", "horror"), group="basic")
def blur(ctx, p):
    e = o_cubic(p)
    return whole(ctx, p, s=1 + 0.18 * (1 - e), a=e ** 0.7)


@part("flicker", "Flicker", ("glitch", "horror"), group="basic")
def flicker(ctx, p):
    step = np.floor(p * 16)
    shown = (p >= 1) | (_r(ctx.seed, step, gi(ctx)) < p * 1.25)
    return out(ctx, p, hide=~shown)


# ---------------- glyph windows (mask kind 9) ----------------

class _Window(_Enter):
    uses_mask = True
    mask_cell = (-2.0, -0.66, 2.0, 0.66)
    move = (0.0, 1.15)                                       # JIZURA's masked(fx, fy) at q = 0, em (y down)

    def ease(self, q):
        return o_quint(q)

    def evaluate(self, ctx, p):
        q = stg(p, ord_lr(ctx), 0.45)
        m = self.ease(q)
        fx, fy = self.move
        return out(ctx, p, dx=fx * (1 - m), dy=fy * (1 - m), hide=q <= 0, live=q < 1, mask=m)

    def mask_shape(self, ctx):
        fx, fy = self.move
        return (9.0, fx, -fy, 0.0)                         # the glyph's offset at m = 0, in glyph x / up


@register("enter", "rise_mask")
class RiseMask(_Window):
    name = "Rise from Below"
    tags = ("editorial", "graphic", "calm", "emotional")
    weight = 1.4


@register("enter", "drop_mask")
class DropMask(_Window):
    name = "Drop from Above"
    tags = ("editorial", "graphic", "pop")
    weight = 1.2
    move = (0.0, -1.15)

    def ease(self, q):
        return o_back(q, 1.35)


@register("enter", "slide_r")
class SlideR(_Window):
    name = "Slide from the Right"
    tags = ("editorial", "graphic", "pop")
    mask_cell = (-0.62, -2.0, 0.62, 2.0)
    move = (1.2, 0.0)


# ---------------- line masks with a plane in front (kinds 5 to 8) ----------------

class _LineMask(_Enter):
    uses_mask = True
    mask_kind = 0.0                    # not `kind`: the registry sets that to "enter"

    def mask_shape(self, ctx):
        return (self.mask_kind, side(ctx, 17), 0.0, 0.0)


@register("enter", "iris")
class Iris(_LineMask):
    """A circle opens from the line's centre, an accent ring on its edge."""
    name = "Iris"
    tags = ("pop", "emotional", "graphic")
    weight = 0.8
    mask_kind = 5.0
    line_fx = True

    def evaluate(self, ctx, p):
        e = o_quart(p)
        d = whole(ctx, p, s=1.14 + (1 - 1.14) * e)
        d.mask = np.broadcast_to(e, p.shape).astype(float).copy()
        return d


@register("enter", "diag_wipe")
class DiagWipe(_LineMask):
    """A slanted edge uncovers the line behind an accent band."""
    name = "Diagonal Wipe"
    tags = ("graphic", "editorial", "pop")
    mask_kind = 6.0
    line_fx = True

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=clip(p))


@register("enter", "blinds")
class Blinds(_LineMask):
    """Thin horizontal slats widen from the top down."""
    name = "Blinds"
    tags = ("graphic", "editorial")
    weight = 0.8
    mask_kind = 7.0

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=clip(p))


@register("enter", "shutter")
class Shutter(_LineMask):
    """Opens from the middle line up and down, between two accent lines."""
    name = "Shutter"
    tags = ("graphic", "editorial")
    mask_kind = 8.0
    line_fx = True

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], mask=clip(p))


# ---------------- band copies (like the slice) ----------------

class _Bands(_Enter):
    """The glyph shows when its copies have landed; design §5.6."""
    band_copies = 1                                          # on; band_count() says how many

    def evaluate(self, ctx, p):
        return Delta(ctx.n, p.shape[1], alpha=(p >= 1).astype(float))


@register("enter", "v_slice")
class VSlice(_Bands):
    """Vertical strips of the line slide in from above and below, the middle ones first."""
    name = "Vertical Slice"
    tags = ("graphic", "glitch")
    band_axis = "x"

    def band_count(self, width_em):
        return int(np.clip(round((width_em + 0.6) / 0.55), 4, 8))

    def band_motion(self, p, b, n, k, g, width, height, em):
        e = o_quint(stg(p, abs(b - (n - 1) / 2) / ((n - 1) / 2) if n > 1 else 0.0, 0.5))
        dist = height * 0.9 + 1.4 * em
        return 0.0 * p, -(1 if b % 2 else -1) * dist * (1 - e)


@register("enter", "split_join")
class SplitJoin(_Bands):
    """Each glyph's top and bottom halves slide together from opposite sides."""
    name = "Halves Join"
    tags = ("graphic", "editorial")
    weight = 0.9

    def band_count(self, width_em):
        return 2

    def band_start(self, b, k, g):
        return 0.4 * (k / (g - 1) if g > 1 else 0.0)

    def band_motion(self, p, b, n, k, g, width, height, em):
        q = stg(p, k / (g - 1) if g > 1 else 0.0, 0.4)
        sgn = 1 if b == 0 else -1                            # bottom half from one side, top from the other
        return sgn * 1.1 * em * (1 - o_quint(q)), 0.0 * p


# ---------------- glyph motions ----------------

@part("slide_l", "Slide from the Left", ("editorial", "calm", "pop"))
def slide_l(ctx, p):
    q = stg(p, ord_lr(ctx), 0.5)
    e = o_quint(q)
    return out(ctx, p, dx=-(1 - e) * 0.85, a=clip(q * 1.6) ** 1.6, hide=q <= 0, live=q < 1)


@part("slide_whole", "Whole Line Slides In", ("pop", "graphic"), 0.9)
def slide_whole(ctx, p):
    e = o_back(p, 1.7)
    dist = (1.3 if ctx.n <= 1 else 3.2) * (0.7 + 0.6 * ctx.strength)
    return out(ctx, p, dx=side(ctx, 11) * dist * (1 - e), a=clip(p * 4), live=p < 1)


@part("flip_x", "Flip on the Upright", ("pop", "graphic", "editorial"))
def flip_x(ctx, p):
    q = stg(p, ord_lr(ctx), 0.45)
    th = (1 - o_back(clip((q - 0.22) / 0.78), 1.25)) * 180
    return out(ctx, p, yaw=th, s=o_back(q / 0.22, 1.6), hide=(q <= 0) | (th > 90), live=q < 1)


@part("flip_y", "Flip on the Horizontal", ("pop", "graphic"), 0.9)
def flip_y(ctx, p):
    q = stg(p, ord_c(ctx), 0.4)
    th = (1 - o_quart(q)) * 270
    shown = np.cos(th * DEG) > 0.04
    return out(ctx, p, pitch=th, a=clip(q * 3), hide=(q <= 0) | ~shown, live=q < 1)


@part("domino", "Domino", ("pop",), 0.7, 0.75)
def domino(ctx, p):
    q = stg(p, ord_lr(ctx), 0.55)
    th = (1 - o_back(q, 1.5)) * 90 * DEG                    # lying on its right side -> upright, pivot bottom-right
    vx, vy = -0.5, -0.5
    c, s = np.cos(th), np.sin(th)
    return out(ctx, p, dx=c * vx - s * vy - vx, dy=s * vx + c * vy - vy, rot=th / DEG, a=clip(q * 4),
               hide=q <= 0, live=q < 1)


@part("fold", "Fold Open", ("graphic", "editorial"), 0.9)
def fold(ctx, p):
    q = stg(p, ord_lr(ctx), 0.5)
    sy = np.maximum(0.02, o_back(q, 1.6))
    dy = np.where(gi(ctx) % 2, 1.0, -1.0) * (1 - sy) / 2
    return out(ctx, p, sy=sy, dy=dy, a=clip(q * 4), hide=q <= 0, live=q < 1)


@part("unroll", "Unroll", ("calm", "editorial", "emotional"), 0.9)
def unroll(ctx, p):
    q = stg(p, ord_lr(ctx), 0.5)
    k = 0.3 + 0.7 * o_cubic(q)
    return out(ctx, p, sx=k, dx=-(1 - k) / 2, hide=q <= 0, live=q < 1)


@part("random_order", "Random Order", ("pop", "glitch"))
def random_order(ctx, p):
    u = clip((p - _r(ctx.seed, gi(ctx), 61) * 0.62) / 0.38)
    return out(ctx, p, s=1.45 + (1 - 1.45) * o_quint(u), a=clip(u * 6), hide=u <= 0, live=u < 1)


@part("bounce_big", "Big Jump", ("pop",), 0.7, 0.95)
def bounce_big(ctx, p):
    q = stg(p, ord_lr(ctx), 0.35)
    s1, s2, s3 = q / 0.5, (q - 0.5) / 0.26, (q - 0.76) / 0.14
    y = np.where(q < 0.5, 7.666 * s1 * s1 - 9.266 * s1 + 1.6,
                 np.where(q < 0.76, -0.24 * 4 * s2 * (1 - s2), np.where(q < 0.9, -0.06 * 4 * s3 * (1 - s3), 0.0)))
    rot = np.where(q < 0.5, _rs(ctx.seed, gi(ctx), 21) * 28 * np.sin(np.pi * clip(s1)), 0.0)
    imp = np.exp(-((q - 0.5) / 0.035) ** 2) + 0.6 * np.exp(-((q - 0.76) / 0.03) ** 2)
    sy, sx = 1 - 0.3 * imp, 1 + 0.24 * imp
    return out(ctx, p, dy=y + (1 - sy) / 2, sy=sy, sx=sx, rot=rot, a=clip(q * 7), hide=q <= 0, live=q < 1)


@part("squash_drop", "Squash Landing", ("pop",), 0.8, 0.75)
def squash_drop(ctx, p):
    q = stg(p, ord_lr(ctx), 0.4)
    t1, t2 = q / 0.22, (q - 0.22) / 0.78
    dy = np.where(q < 0.22, -(1 - t1 * t1) * 1.7, 0.0)
    sy = np.where(q < 0.22, 1 + 0.4 * t1, 1 - 0.58 * np.exp(-3 * t2) * np.cos(t2 * 6.2) * (1 - t2))
    return out(ctx, p, dy=dy + (1 - sy) / 2, sy=sy, sx=1 / np.maximum(sy, 0.05) ** 0.8, a=clip(q * 10),
               hide=q <= 0, live=q < 1)


@part("rubber", "Rubber Stretch", ("pop",), 0.8, 0.75)
def rubber(ctx, p):
    q = stg(p, ord_lr(ctx), 0.4)
    f = (1 - q) ** 2 * np.cos(q * 3.5 * np.pi)
    sx = np.maximum(0.03, 1 - f)
    return out(ctx, p, sx=sx, sy=np.clip(1 + (1 - sx) * 0.45, 0.72, 1.45), a=clip(q * 6), hide=q <= 0, live=q < 1)


@part("whip", "Whip", ("pop", "graphic"), 1.0, 0.45)
def whip(ctx, p):
    d = side(ctx, 19)
    e = out_expo(p)
    width = float(np.ptp(centred(ctx)[0])) + 1
    lean = d * 34 * (1 - e) ** 0.7 * 0.4                     # the skew becomes a lean
    return out(ctx, p, dx=d * max(4.5, width * 0.9) * (1 - e), rot=lean, a=clip(p * 8), live=p < 1)


@part("skew_in", "Slanted Entry", ("editorial", "graphic"), 0.9)
def skew_in(ctx, p):
    d = side(ctx, 23)
    q = stg(p, ord_lr(ctx), 0.45)
    sk = np.clip(d * 60 * (1 - o_back(q, 1.6)), -66, 66)
    return out(ctx, p, rot=sk * 0.4, dx=d * (1 - o_quint(q)) * 0.7, a=clip(q * 3), hide=q <= 0, live=q < 1)


@part("track_in", "Spacing Closes In", ("calm", "editorial", "emotional"), 1.2)
def track_in(ctx, p):
    e = o_quint(p)
    cx, _ = centred(ctx)
    return out(ctx, p, dx=cx * 1.6 * (1 - e) / max(1, ctx.n / 4) if ctx.n > 1 else 0.9 * (1 - e),
               a=out_cubic(clip(p * 1.7)), live=p < 1)


@part("track_out", "Spacing Opens Out", ("calm", "editorial", "pop"))
def track_out(ctx, p):
    e = o_quint(p)
    cx, _ = centred(ctx)
    return out(ctx, p, dx=-cx * 0.72 * (1 - e) / max(1, ctx.n / 4), a=clip(p * 2.5) * (0.55 + 0.45 * e), live=p < 1)


@part("blur_stagger", "Blur by Letter", ("calm", "emotional"), 1.2)
def blur_stagger(ctx, p):
    q = stg(p, ord_lr(ctx), 0.55)
    e = out_cubic(q)
    return out(ctx, p, a=e ** 0.6, s=1.35 + (1 - 1.35) * e, dy=-(1 - e) * 0.16, hide=q <= 0, live=q < 1)


@part("fade_stagger", "Fade by Letter", ("calm", "emotional"), 1.2, 0.85)
def fade_stagger(ctx, p):
    q = stg(p, ord_lr(ctx), 0.62)
    return out(ctx, p, a=in_out_sine(q), dy=(1 - out_cubic(q)) * 0.07, hide=q <= 0, live=q < 1)


@part("wave_in", "Rippling In", ("pop", "emotional"), 0.9, 0.85)
def wave_in(ctx, p):
    damp = (1 - clip(p)) ** 1.6
    a = clip(p * 2.4 - ord_lr(ctx) * 1.3)
    ph = p * 3.6 * np.pi - gi(ctx) * 0.8
    return out(ctx, p, dy=-np.sin(ph) * 0.66 * damp, rot=np.cos(ph) * 13 * damp, a=a, hide=a <= 0, live=p < 1)


@part("spiral_in", "Spiral Gather", ("pop", "emotional"), 0.7, 0.75)
def spiral_in(ctx, p):
    q = stg(p, ord_lr(ctx), 0.15)
    k = 1 - out_cubic(q)
    d = side(ctx, 29)
    px, pz = centred(ctx)
    py = -pz
    ang = d * k * 200 * DEG
    c, s = np.cos(ang), np.sin(ang)
    r = 1 + 0.7 * k
    th = _r(ctx.seed, gi(ctx), 31) * TAU + ang
    nx, ny = (c * px - s * py) * r + np.cos(th) * k, (s * px + c * py) * r + np.sin(th) * k
    return out(ctx, p, dx=nx - px, dy=ny - py, rot=d * k * 320, s=0.45 + 0.55 * (1 - k), a=clip(q * 5),
               hide=q <= 0, live=q < 1)


@part("zoom_out", "Huge to Normal", ("pop", "graphic", "glitch"))
def zoom_out(ctx, p):
    e = out_expo(p)
    dip = 0.035 * np.sin(np.pi * clip((p - 0.22) / 0.58))
    return whole(ctx, p, s=1 + 3.4 * (1 - e) - dip, a=clip(p * 6))


@part("magnet", "Magnet", ("pop", "graphic"), 0.8, 0.85)
def magnet(ctx, p):
    i = gi(ctx)
    u = clip((p - (_r(ctx.seed, i, 81) * 0.3 if ctx.n > 1 else 0.0)) / 0.7)
    ang, dist = _r(ctx.seed, i, 82) * TAU, 1.3 + 1.5 * _r(ctx.seed, i, 83)
    rot0 = _rs(ctx.seed, i, 84) * 55
    t1, t2, t3 = u / 0.36, (u - 0.36) / 0.24, (u - 0.6) / 0.4
    f = np.where(u < 0.36, 1 - 0.16 * o_cubic(t1), np.where(u < 0.6, 0.84 * (1 - in_cubic(t2)),
                                                           -0.1 * np.sin(t3 * TAU) * (1 - t3)))
    a = np.where(u < 0.36, 0.5 * clip(u * 8), np.where(u < 0.6, 0.5 + 0.5 * clip(t2 * 3), 1.0))
    s = 1 + 0.14 * np.exp(-((u - 0.6) / 0.05) ** 2)
    return out(ctx, p, dx=np.cos(ang) * dist * f, dy=np.sin(ang) * dist * f, rot=rot0 * f, s=s, a=a,
               hide=u <= 0, live=u < 1)


@part("neon_on", "Neon Lighting Up", ("glitch", "emotional", "pop"), 0.8, 0.9)
def neon_on(ctx, p):
    i = gi(ctx)
    ig = 0.3 + 0.45 * _r(ctx.seed, i, 101)
    step = np.floor(p * 16)
    on = _r(ctx.seed, i, step, 102) < 0.25 + 0.75 * clip((p - ig + 0.22) / 0.34)
    a = np.where(p < ig - 0.22, 0.1 * clip(p * 8), np.where(on, 1.0, 0.1))
    return out(ctx, p, a=a, live=p < ig + 0.12)


@part("stamp", "Stamp", ("pop", "graphic"), 0.9, 0.7)
def stamp(ctx, p):
    d = side(ctx, 37)
    ti = 0.42
    t = clip(p / ti) ** 2
    t2 = (p - ti) / (1 - ti)
    dec = (1 - clip(t2)) ** 2
    step = np.floor(p * 16)
    first = p < ti
    s = np.where(first, 2.3 + (1 - 2.3) * t, 1 - 0.05 * np.exp(-clip(t2) * 9) * (1 - clip(t2)))
    rot = np.where(first, d * -22 * (1 - t), 0.0)
    dx = np.where(first, 0.0, _rs(ctx.seed, step, 1) * 0.05 * dec)
    dy = np.where(first, 0.0, _rs(ctx.seed, step, 2) * 0.03 * dec)
    d0 = whole(ctx, p, s=s, rot=rot, a=np.where(first, clip(p / ti * 3), 1.0))
    d1 = out(ctx, p, dx=dx, dy=dy, live=p < 1)
    return d0.then(d1)


@part("spring_in", "Spring Bounce", ("pop",), 0.9, 0.8)
def spring_in(ctx, p):
    q = stg(p, ord_lr(ctx), 0.45)
    f = spring(q, 4.2, 3)
    v = (spring(q + 0.01, 4.2, 3) - f) / 0.01
    st = 1 + np.minimum(0.5, np.abs(v) * 0.075)
    return out(ctx, p, dy=f * 1.7, sy=st, sx=1 / np.sqrt(st), a=clip(q * 6), hide=q <= 0, live=q < 1)


@part("pendulum", "Pendulum", ("pop", "emotional", "calm"), 0.9, 0.9)
def pendulum(ctx, p):
    d = side(ctx, 41)
    q = stg(p, ord_lr(ctx), 0.45)
    th = d * 62 * spring(q, 3.1, 2.4)
    r, length = th * DEG, 0.5 + 0.45
    return out(ctx, p, dx=-length * np.sin(r), dy=length * np.cos(r) - length, rot=th, a=clip(q * 5),
               hide=q <= 0, live=q < 1)


@part("roll_in", "Rolling In", ("pop", "graphic"), 0.9)
def roll_in(ctx, p):
    d = side(ctx, 43)
    q = stg(p, ord_rl(ctx) if d < 0 else ord_lr(ctx), 0.22)
    off = d * 2.3 * (0.75 + 0.4 * ctx.strength) * (1 - o_back(q, 1.25))
    return out(ctx, p, dx=off, rot=-off / 0.5 / DEG,               # rolls along: the arc it covers / its radius
               s=0.72 + 0.28 * o_cubic(q), a=clip(q * 5), hide=q <= 0, live=q < 1)


@part("slingshot", "Slingshot", ("pop", "graphic"), 0.7, 0.9)
def slingshot(ctx, p):
    ta = 0.36
    t1, t2 = clip(p / ta), clip((p - ta) / (1 - ta))
    f = np.where(p < ta, 0.2 + 0.8 * out_cubic(t1), spring(t2, 4.6, 2.6))
    v = (spring(t2 + 0.01, 4.6, 2.6) - spring(t2, 4.6, 2.6)) / 0.01
    along = np.where(p < ta, 1 - 0.14 * out_cubic(t1), 1 + np.minimum(0.4, np.abs(v) * 0.05))
    across = np.where(p < ta, 1 + 0.07 * out_cubic(t1), 1 / np.sqrt(along))
    return whole(ctx, p, sx=across, sy=along, dy=f * 1.05, a=np.where(p < ta, clip(t1 * 3), 1.0))


@part("rock_settle", "Rocking Landing", ("pop",), 0.8, 0.9)
def rock_settle(ctx, p):
    q = stg(p, ord_lr(ctx), 0.4)
    i = gi(ctx)
    th0 = np.where(_r(ctx.seed, i, 45) < 0.5, -1.0, 1.0) * (16 + 10 * _r(ctx.seed, i, 46))
    t1, t2 = q / 0.3, (q - 0.3) / 0.7
    th = np.where(q < 0.3, th0, th0 * (1 - clip(t2)) ** 1.5 * np.cos(np.pi * (1.4 * t2 + 1.9 * t2 * t2)))
    dy = np.where(q < 0.3, -(1 - t1 * t1) * 2.0, 0.0)
    r = th * DEG
    c, s = np.cos(r), np.sin(r)
    cx = np.where(th >= 0, 0.5, -0.5)
    return out(ctx, p, dx=cx - (cx * c - 0.5 * s), dy=dy + 0.5 - (cx * s + 0.5 * c), rot=th, a=clip(q * 8),
               hide=q <= 0, live=q < 1)


@part("bounce_ball", "Bouncing Ball", ("pop", "emotional"), 0.8, 1.0)
def bounce_ball(ctx, p):
    n = ctx.n
    k = gi(ctx)
    hit = 0.16 + 0.6 * k / (n - 1) if n > 1 else np.full((n, 1), 0.45)
    u = (p - hit) / 0.2
    sq = 0.55 + 0.45 * o_back(u, 2.4)
    return out(ctx, p, sy=sq, sx=1 + 0.3 * (1 - o_quint(u)), dy=(1 - sq) / 2, hide=p < hit, live=u < 1)


@part("snap_rail", "Snap into Line", ("graphic", "pop", "editorial"), 0.9, 0.9)
def snap_rail(ctx, p):
    i = gi(ctx)
    a = clip((p - _r(ctx.seed, i, 53) * 0.2) / 0.2)
    ts = 0.46 + _r(ctx.seed, i, 54) * 0.06
    sgn = np.where(_r(ctx.seed, i, 51) < 0.5, -1.0, 1.0)
    off0, rot0 = sgn * (0.3 + 0.6 * _r(ctx.seed, i, 52)), _rs(ctx.seed, i, 55) * 16
    t = (p - ts) / 0.13
    u = clip((t - 1) / 1.6)
    e = in_cubic(t)
    off = np.where(p < ts, off0 * (1 - 0.14 * (p / ts)),
                   np.where(t < 1, off0 * 0.86 * (1 - e), -sgn * 0.06 * np.sin(np.pi * u) * (1 - u)))
    rot = np.where(p < ts, rot0 * (1 - 0.14 * (p / ts)), np.where(t < 1, rot0 * 0.86 * (1 - e), 0.0))
    sq = np.where((p >= ts) & (t >= 1), 1 - 0.16 * np.sin(np.pi * clip(u * 2)) * (1 - u), 1.0)
    return out(ctx, p, dy=off, rot=rot, sy=sq, sx=1 / np.sqrt(sq), a=a, hide=a <= 0, live=u < 1)


@part("fan_open", "Fan Opening", ("emotional", "graphic", "calm"), 0.9, 0.8)
def fan_open(ctx, p):
    cx, cz = centred(ctx)
    gx, gy = cx, -cz
    x0 = float(cx.min()) if ctx.n else 0.0
    r0 = 0.8 + 0.5
    pvx, pvy = x0 + 0.5, float(gy.max()) + r0
    vx, vy = gx - pvx, gy - pvy
    a_min = float(np.arctan2(vy, vx).min()) if ctx.n else 0.0
    e = o_back(p, 1.15)
    d = (a_min - 0.45 - np.arctan2(vy, vx)) * (1 - e)
    c, s = np.cos(d), np.sin(d)
    nx, ny = c * vx - s * vy, s * vx + c * vy
    return out(ctx, p, dx=nx - vx, dy=ny - vy, rot=d / DEG, a=clip(p * 3.5), live=p < 1)


@part("cylinder", "Cylinder Turn", ("graphic", "pop", "editorial"), 0.9)
def cylinder(ctx, p):
    cx, _ = centred(ctx)
    width = float(np.ptp(cx)) + 1
    r = max(0.6, width / 2) / 1.2
    phi = side(ctx, 61) * (1 - o_quart(p)) * 2.4
    flat = smooth(0.5, 1, p)
    th = cx / r + phi
    cu = np.cos(th)
    nu = r * np.sin(th) + (cx - r * np.sin(th)) * flat
    k = np.maximum(0.04, cu) + (1 - np.maximum(0.04, cu)) * flat
    a = clip(p * 6) * (clip(cu * 1.6) + (1 - clip(cu * 1.6)) * flat)
    return out(ctx, p, dx=nu - cx, sx=k, a=a, hide=(cu <= 0.04) & (flat < 0.5), live=p < 1)


@part("stop_motion", "Stop Motion", ("pop", "emotional"), 0.8, 0.8)
def stop_motion(ctx, p):
    i = gi(ctx)
    q = stg(p, _r(ctx.seed, i, 81) * 0.5 + ord_lr(ctx) * 0.5, 0.45)
    k = np.minimum(4, np.floor(q * 5))
    f = 1 - o_cubic(k / 4)
    ang, dist = _r(ctx.seed, i, 82) * TAU, 0.7 + 0.5 * _r(ctx.seed, i, 83)
    return out(ctx, p, dx=np.cos(ang) * dist * f + _rs(ctx.seed, i, k, 84) * 0.05,
               dy=np.sin(ang) * dist * f + _rs(ctx.seed, i, k, 85) * 0.05,
               rot=_rs(ctx.seed, i, k, 86) * 22 * f + _rs(ctx.seed, i, 87) * 6 * f, s=1 + _rs(ctx.seed, i, k, 88) * 0.14 * f,
               hide=q <= 0, live=k < 4)


@part("ripple", "Ripple", ("emotional", "calm", "graphic"))
def ripple(ctx, p):
    cx, cz = centred(ctx)
    vx, vy = cx, -cz
    d = np.hypot(vx, vy)
    rmax = float(d.max()) + 0.8 if ctx.n else 1.0
    q = clip((p - 0.68 * d / rmax) / 0.32)
    push = 0.28 * np.sin(q * np.pi * 2) * (1 - q) ** 2
    dd = np.maximum(d, 1e-6)
    far = d > 1
    return out(ctx, p, s=1 + 0.4 * np.sin(q * np.pi) * (1 - q), a=clip(q * 5), dx=np.where(far, vx / dd * push, 0.0),
               dy=np.where(far, vy / dd * push, 0.0), hide=q <= 0, live=q < 1)


@part("zoom_alt", "Alternate Zoom", ("pop", "graphic", "glitch"), 0.9)
def zoom_alt(ctx, p):
    q = stg(p, ord_lr(ctx), 0.35)
    even = gi(ctx) % 2 == 0
    s = np.where(even, 2.4 + (1 - 2.4) * o_quint(q), np.maximum(0.02, o_back(q, 2.2)))
    return out(ctx, p, s=s, a=np.where(even, clip(q * 2.5), clip(q * 4)), hide=q <= 0, live=q < 1)


@part("wind_blown", "Carried by the Wind", ("emotional", "calm"), 0.8, 0.9)
def wind_blown(ctx, p):
    d = side(ctx, 191)
    q = stg(p, ord_rl(ctx) if d > 0 else ord_lr(ctx), 0.5)
    k = 1 - o_cubic(q)
    ph = _r(ctx.seed, gi(ctx), 193) * TAU
    return out(ctx, p, dx=-d * 4.0 * k, dy=np.sin(ph + k * 6) * 0.5 * k, rot=np.sin(ph * 2 + k * 7) * 120 * k,
               a=clip(q * 4), hide=q <= 0, live=q < 1)


# ---------------- horror ----------------

@part("hr_blink_creep", "Between Blinks", ("horror", "emotional"), 0.9, 1.3, group="horror")
def hr_blink_creep(ctx, p):
    blinks = (0.26, 0.52, 0.78)
    dark = np.zeros_like(p, dtype=bool)
    stage = np.zeros_like(p)
    for b in blinks:
        dark |= (p >= b) & (p < b + 0.05)
        stage += p >= b + 0.05
    r = 1 - stage / 3
    k = h_np(ctx.seed, np.round(ord_lr(ctx) * 97), 11)
    ang, dist = _r(k, 1) * TAU, 0.9 + _r(k, 2) * 1.1
    return out(ctx, p, dx=np.cos(ang) * dist * r, dy=np.sin(ang) * dist * r * 0.6, s=1 - 0.45 * r,
               rot=_rs(k, 3) * 25 * r, a=0.3 + 0.7 * (1 - r), hide=dark, live=r > 0)


@part("hr_uneasy", "Uneasy Timing", ("horror", "editorial"), 1.0, 1.6, group="horror")
def hr_uneasy(ctx, p):
    gaps = 0.2 + _r(ctx.seed, np.arange(ctx.n), 21) ** 2             # irregular gaps between the letters
    times = (np.cumsum(gaps) - gaps[0]) / max(float(np.sum(gaps) - gaps[0]), 1e-6) * 0.86 if ctx.n > 1 else np.zeros(1)
    q = (p - times[:, None]) / 0.1
    k = h_np(ctx.seed, gi(ctx), 21)
    return out(ctx, p, dx=_rs(k, 1) * 0.18 * (1 - q), dy=_rs(k, 2) * 0.1 * (1 - q), rot=_rs(k, 3) * 18 * (1 - q),
               hide=q < 0, live=q < 1)


@part("hr_manifest", "Surfacing", ("horror", "emotional", "calm"), 1.0, 1.4, group="horror")
def hr_manifest(ctx, p):
    fin = smooth(0.72, 1, p)
    k = h_np(ctx.seed, gi(ctx), 31)
    ph, f = _r(k, 1) * TAU, 7 + _r(k, 2) * 6
    wav = clip(p * 1.3) * (0.45 + 0.55 * np.maximum(0, np.sin(p * f + ph)))
    a = wav + (1 - wav) * fin
    return out(ctx, p, a=a, dx=noise1_np(p * 4 + ph, k) * 0.12 * (1 - fin), dy=noise1_np(p * 3 + ph, k + 1) * 0.08 * (1 - fin),
               live=a < 0.999)


# ---------------- kinetic (word by word) ----------------

def words(ctx):
    """Per glyph: word index (G, 1), number of words, word centre / left / bottom x and z in em (G, 1)."""
    w = np.zeros(ctx.n, dtype=int) if ctx.words is None or len(ctx.words) != ctx.n else np.asarray(ctx.words, dtype=int)
    cx, cz = centred(ctx)
    wc, wl, wr, wb = (np.zeros((ctx.n, 1)) for _ in range(4))
    for j in np.unique(w):
        sel = w == j
        wc[sel] = (cx[sel].max() + cx[sel].min()) / 2
        wl[sel], wr[sel] = cx[sel].min() - 0.5, cx[sel].max() + 0.5
        wb[sel] = cz[sel].min() - 0.5
    return w[:, None], int(w.max()) + 1 if ctx.n else 1, cx, cz, wc, wl, wr, wb


def out_elastic(x):
    x = clip(x)
    c4 = TAU / 3
    with np.errstate(over="ignore"):
        v = 2.0 ** (-10 * x) * np.sin((x * 10 - 0.75) * c4) + 1
    return np.where(x <= 0, 0.0, np.where(x >= 1, 1.0, v))


def _word_q(p, j, n, sp):
    return stg(p, j / (n - 1) if n > 1 else 0.0, sp if n > 1 else 0.0)


def _turn(px, pz, cx, cz, deg):
    """(dx, dy) moving a point (px, pz) turned clockwise by deg about (cx, cz); dy down, em."""
    r = deg * DEG
    x, z = px - cx, pz - cz
    nx, nz = np.cos(r) * x + np.sin(r) * z, -np.sin(r) * x + np.cos(r) * z
    return nx - x, -(nz - z)


@part("kn_word_slam", "Word Slam", ("pop", "graphic", "glitch"), 1.1, 1.0, group="kinetic")
def kn_word_slam(ctx, p):
    j, n, cx, cz, wc, *_ = words(ctx)
    q = _word_q(p, j, n, 0.62)
    e = out_expo(clip(q * 1.35))
    s = 1 + 2.1 * (1 - e)
    return out(ctx, p, s=s, dx=(cx - wc) * (s - 1), dy=-cz * (s - 1), a=clip(q * 7),
               rot=(1 - e) * np.where(j % 2, 7.0, -7.0), hide=q <= 0, live=e < 1)


@part("kn_hinge_drop", "Hinged Drop", ("pop", "graphic"), 0.9, 1.0, group="kinetic")
def kn_hinge_drop(ctx, p):
    j, n, cx, cz, wc, wl, wr, wb = words(ctx)
    d = 1.0 if h_np(ctx.seed, 61) & 1 else -1.0
    q = _word_q(p, j, n, 0.5)
    th = -88 * d * (1 - bounce(q))
    px = wl if d > 0 else wr
    dx, dy = _turn(cx, cz, px, wb, th)
    return out(ctx, p, dx=dx, dy=dy, rot=th, a=clip(q * 6), hide=q <= 0, live=q < 1)


@part("kn_inertia", "Sudden Brake", ("pop", "graphic"), 0.9, 0.8, group="kinetic")
def kn_inertia(ctx, p):
    d = 1.0 if h_np(ctx.seed, 67) & 1 else -1.0
    back = (1 - ord_lr(ctx)) if d > 0 else ord_lr(ctx)
    q = clip((p - back * 0.3) / 0.7)
    e = o_back(q, 2.1)
    v = (o_back(np.minimum(1, q + 0.02), 2.1) - e) / 0.02
    st = 1 + np.minimum(0.5, np.abs(v) * 0.08)
    bell = np.sin(np.pi * clip((q - 0.55) / 0.45))
    sq = np.where(q > 0.55, 1 - 0.18 * back * bell, 1.0)
    return out(ctx, p, dx=-d * 6.0 * (1 - e), sx=st * sq, sy=1 / st, live=q < 1)


@part("kn_word_spin", "Word Spin", ("pop", "graphic"), 0.9, 1.0, group="kinetic")
def kn_word_spin(ctx, p):
    j, n, cx, cz, wc, *_ = words(ctx)
    q = _word_q(p, j, n, 0.5)
    s = 0.15 + 0.85 * o_back(q, 1.6)
    th = (1 - o_cubic(q)) * 200 * np.where(j % 2, -1.0, 1.0)
    dx, dy = _turn((cx - wc) * s + wc, cz * s, wc, 0.0, th)
    return out(ctx, p, dx=(cx - wc) * (s - 1) + dx, dy=-cz * (s - 1) + dy, rot=th, s=s, a=clip(q * 5),
               hide=q <= 0, live=q < 1)


@part("kn_stretch_out", "Stretching Out", ("pop", "graphic"), 0.9, 1.0, group="kinetic")
def kn_stretch_out(ctx, p):
    j, n, cx, cz, wc, wl, *_ = words(ctx)
    q = _word_q(p, j, n, 0.55)
    s = np.where(q >= 1, 1.0, np.maximum(0.02, out_elastic(q)))
    return out(ctx, p, dx=(cx - wl) * (s - 1), sx=s, a=clip(q * 8), hide=q <= 0, live=q < 1)


# ---------------- typography ----------------

def key_glyph(ctx):
    """The glyph that carries the line: the first kanji, else the middle one."""
    for i, ch in enumerate(getattr(ctx, "chars", None) or ()):
        if "一" <= ch <= "鿿" or ch == "々":
            return i
    return ctx.n // 2


@part("ty_key_first", "Key Letter First", ("pop", "graphic", "editorial", "emotional"), 1.0, 0.6, group="typo")
def ty_key_first(ctx, p):
    ki = key_glyph(ctx)
    cx, cz = centred(ctx)
    i = gi(ctx)
    kq = clip(p / 0.42)
    md = max(1.0, float(np.abs(i - ki).max())) if ctx.n else 1.0
    q = clip((p - 0.3 - np.abs(i - ki) / md * 0.35) / 0.35)
    e = out_expo(q)
    key = i == ki
    kx, kz = (cx[ki, 0], cz[ki, 0]) if ctx.n else (0.0, 0.0)
    return out(ctx, p, s=np.where(key, 2.1 + (1 - 2.1) * out_expo(kq), 0.4 + 0.6 * e),
               dx=np.where(key, 0.0, (kx - cx) * (1 - e)), dy=np.where(key, 0.0, -(kz - cz) * (1 - e)),
               a=np.where(key, clip(kq * 4), clip(q * 2.5)), hide=np.where(key, kq <= 0, q <= 0),
               live=np.where(key, kq < 1, q < 1))


@part("ty_zoom_one", "One Letter at a Time", ("pop", "graphic", "emotional"), 0.8, 1.5, group="typo")
def ty_zoom_one(ctx, p):
    n = ctx.n
    cx, cz = centred(ctx)
    big = 2.0
    span = min(0.55, 2.2 / (n + 1)) if n > 1 else 1.0
    s0 = gi(ctx) / (n - 1) * (1 - span) if n > 1 else np.zeros((n, 1))
    q = clip((p - s0) / span)
    first = q < 0.38
    u = out_cubic(q / 0.38)
    e = io_cubic((q - 0.38) / 0.62)
    return out(ctx, p, dx=np.where(first, -cx, -cx * (1 - e)), dy=np.where(first, cz, cz * (1 - e)),
               s=np.where(first, big * 1.25 + (big - big * 1.25) * u, big + (1 - big) * e),
               a=np.where(first, clip(q / 0.1), 1.0), hide=q <= 0, live=q < 1)
