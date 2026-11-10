# Layouts ported from JIZURA (src/06_layouts.js, src/11p_layoutsA-D.js, src/11p_horror*.js, src/11p_kinetic*.js),
# MIT License, Copyright (c) 2026 hakoniwa. Rewritten as arrangements on a board in front of the viewer.
"""Layouts added from JIZURA v0.10 (spec §7.3, design §5.6).

JIZURA composes chunks of the lyric (size, place, turn, horizontal or vertical) on a 2D screen and adds plates,
frames and rules. Here a _Panel puts the same arrangement on a board that faces the viewer at the line's place;
the decorations are left out. compose() returns glyphs as G(char index, x, y, size, rot, depth, extra, vert):
x / y / depth in em at size 1 (y up, depth away from the viewer), rot in degrees clockwise. The board is shrunk
to fit max_w x max_h degrees and never grows past the line's em."""
import math
from collections import namedtuple

import numpy as np

from .. import lyrics, xform
from ..registry import GlyphPlacement, LayoutPart, Placement, register
from .common import DEG, vertical_rot, visible

G = namedtuple("G", "i x y s rot depth extra vert", defaults=(1.0, 0.0, 0.0, None, False))


# ---------------- text helpers ----------------

def chars(ctx):
    return [i for i, ch in enumerate(ctx.text) if visible(ch)]


def n_vis(text):
    return sum(1 for ch in text if visible(ch))


def width(ctx, a, b):
    return sum(ctx.adv[a:b])


def units(ctx, k):
    """The line split into k chunks [(a, b)] of character indices of about the same length, cut at phrase
    boundaries where one is near (JIZURA's splitK)."""
    k = max(1, min(k, n_vis(ctx.text)))
    if any(lyrics.is_latin(c) for c in ctx.text):
        k = min(k, len(ctx.text.split()))                         # whole words only
    vis = [i for i, ch in enumerate(ctx.text) if visible(ch)]
    bounds = {b for a, b in _phrases(ctx)[:-1]}
    cuts = []
    for j in range(1, k):
        ideal = vis[round(j * len(vis) / k)]                         # cut before this glyph
        tol = 1e9 if any(lyrics.is_latin(c) for c in ctx.text) else max(1.0, len(vis) / k * 0.6)   # never inside a word
        near = [b for b in bounds if abs(n_vis(ctx.text[:b]) - n_vis(ctx.text[:ideal])) <= tol
                and (not cuts or b > cuts[-1])]
        cut = min(near, key=lambda b: abs(n_vis(ctx.text[:b]) - n_vis(ctx.text[:ideal]))) if near else \
            _soft_cut(ctx.text, ideal, cuts[-1] if cuts else 0)
        if cuts and cut <= cuts[-1] or n_vis(ctx.text[cuts[-1] if cuts else 0:cut]) == 0:
            cut = ideal
        cuts.append(cut)
    edges = [0] + cuts + [len(ctx.text)]
    out = [(a, b) for a, b in zip(edges, edges[1:]) if n_vis(ctx.text[a:b])]
    return out or [(0, len(ctx.text))]


def _soft_cut(text, ideal, after):
    """A cut near ideal inside a phrase, where a word most likely starts (JIZURA's split2 scores)."""
    def score(c):
        a, b = text[c - 1], text[c]
        v = -abs(c - ideal) * 0.9
        if lyrics.is_hira(a) and not lyrics.is_hira(b) and not lyrics.is_small_kana(b) and b != "ー":
            v += 3
        if lyrics.is_small_kana(b) or lyrics.is_punct(b) or b == "ー":
            v -= 6
        if lyrics.is_kanji(a) and lyrics.is_kanji(b):
            v -= 2
        return v
    cands = [c for c in range(max(after + 1, ideal - 2), min(len(text), ideal + 3)) if visible(text[c])]
    return max(cands, key=score) if cands else ideal


def _phrases(ctx):
    """The phrase chunks of the line as [(a, b)]."""
    out, pos = [], 0
    for c in (ctx.chunks or [ctx.text]):
        at = ctx.text.find(c, pos)
        at = pos if at < 0 else at
        if at > pos and out:
            out[-1] = (out[-1][0], at)
        out.append((at, at + len(c)))
        pos = at + len(c)
    if not out:
        return [(0, len(ctx.text))]
    out[0] = (0, out[0][1])
    out[-1] = (out[-1][0], len(ctx.text))
    return out


def turn(x, y, deg):
    """(x, y) turned clockwise by deg."""
    r = deg * DEG
    return x * math.cos(r) + y * math.sin(r), -x * math.sin(r) + y * math.cos(r)


def run_h(ctx, a, b, x, y, s=1.0, rot=0.0, align="c", depth=0.0):
    """A horizontal run of characters a..b at (x, y) (centre, or left / right edge), turned by rot."""
    w = width(ctx, a, b) * s
    pos = {"c": -w / 2, "l": 0.0, "r": -w}[align]
    out = []
    for i in range(a, b):
        adv = ctx.adv[i] * s
        if visible(ctx.text[i]):
            dx, dy = turn(pos + adv / 2, 0.0, rot)
            out.append(G(i, x + dx, y + dy, s, rot, depth))
        pos += adv
    return out


def run_v(ctx, a, b, x, y, s=1.0, top=False, depth=0.0):
    """A vertical column of characters a..b centred at (x, y) (or hanging from y), JIZURA's vertical rules."""
    h = sum(ctx.vadv[a:b]) * s
    z = y if top else y + h / 2
    out = []
    for i in range(a, b):
        ch, adv = ctx.text[i], ctx.vadv[i] * s
        dx = dz = 0.0
        if lyrics.is_small_kana(ch):
            dx, dz = 0.11 * s, 0.11 * s
        if ch in "、。，．":
            dx, dz = 0.3 * s, 0.3 * s
        if visible(ch):
            out.append(G(i, x + dx, z - adv / 2 + dz, s, 0.0, depth, None,
                         ch in lyrics.VERT_ROTATE or lyrics.is_latin(ch)))
        z -= adv
    return out


def lines(ctx, per):
    """The line broken into rows of about per characters, by phrase."""
    return units(ctx, max(1, math.ceil(n_vis(ctx.text) / per)))


def key_char(ctx):
    """The glyph that carries the line: the first kanji, else the middle one."""
    vis = chars(ctx)
    for i in vis:
        if lyrics.is_kanji(ctx.text[i]):
            return i
    return vis[len(vis) // 2] if vis else 0


def persp(ctx, depth):
    """How much bigger something depth em further back must be to look the same size."""
    return 1 + depth * ctx.em / max(ctx.distance, 1e-6)


def shrink(g, k):
    return g._replace(x=g.x * k, y=g.y * k, s=g.s * k)


# ---------------- the board ----------------

class _Panel(LayoutPart):
    group = "extra"
    max_w = 60.0                  # degrees the board may span across
    max_h = 34.0                  # and up
    scale = 1.0                   # times the context em at most
    azimuth = 0.0                 # board offset from the line's place (degrees; params["side"] flips it)
    elevation = 0.0
    tilt = 0.0                    # board laid back by this many degrees
    turn_board = None             # (yaw degrees) the whole board turned about its vertical axis
    keepable = False              # boards are taller and wider than a row: only one-row ones go to the side slots

    def compose(self, ctx, params):
        raise NotImplementedError

    def motion(self, ctx, params, t):
        """Optional board motion: t (T,) -> (roll degrees (T,), offset in board em (T, 2)) or None."""
        return None

    def place(self, ctx, params):
        gl = self.compose(ctx, params)
        if not gl:
            return Placement(np.zeros(3), xform.IDENTITY.copy(), ctx.em, [])
        x0 = min(g.x - g.s * 0.55 for g in gl)
        x1 = max(g.x + g.s * 0.55 for g in gl)
        y0 = min(g.y - g.s * 0.55 for g in gl)
        y1 = max(g.y + g.s * 0.55 for g in gl)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d = ctx.distance
        lim = lambda deg: 2 * d * math.tan(deg * DEG / 2)
        em = min(ctx.em * self.scale, lim(self.max_w) / max(x1 - x0, 1e-6), lim(self.max_h) / max(y1 - y0, 1e-6))
        side = params.get("side", 1)
        az = ctx.anchor[0] + side * self.azimuth * DEG
        el = ctx.anchor[1] + self.elevation * DEG
        loc = np.array([0.0, 0.0, ctx.eye]) + d * xform.direction(az, el)
        rot = xform.facing(az, el)
        if self.turn_board:
            rot = xform.mul(rot, xform.yaw(side * self.turn_board * DEG))
        if self.tilt:
            rot = xform.mul(rot, xform.pitch(-self.tilt * DEG))
        glyphs = []
        for g in gl:
            q = xform.roll(g.rot * DEG)
            if g.vert:
                q = xform.mul(q, vertical_rot())
            if g.extra is not None:
                q = xform.mul(g.extra, q)
            glyphs.append(GlyphPlacement(g.i, np.array([(g.x - cx) * em, g.depth * em, (g.y - cy) * em]), q, g.vert,
                                         float(g.s)))
        params["_em"] = float(em)
        return Placement(loc, rot, em, glyphs)

    def group_motion(self, ctx, params, placement, t):
        m = self.motion(ctx, params, t)
        if m is None:
            return None
        ang, off = m
        em = params.get("_em", placement.em)
        local = np.stack([off[:, 0] * em, np.zeros(len(t)), off[:, 1] * em], axis=-1)
        loc = placement.loc + xform.rotate(np.broadcast_to(placement.rot, (len(t), 4)), local)
        return loc, xform.mul(placement.rot, xform.roll(np.asarray(ang) * DEG))


def panel(key, name, tags, weight=1.0, fits=(1, 99), group="extra", base=None, **attrs):
    """Register a _Panel (or base) whose compose(ctx, params) is the decorated function; attrs override the class."""
    lo, hi = fits

    def deco(fn):
        body = {"name": name, "tags": tuple(tags), "weight": weight, "group": group,
                "fits": lambda self, n: lo <= n <= hi, "compose": lambda self, ctx, params: fn(ctx, params)}
        body.update({k: v for k, v in attrs.items() if k != "plan"})
        if "plan" in attrs:
            plan = attrs["plan"]
            body["plan"] = lambda self, rng, ctx: plan(rng, ctx)
        cls = type(f"L_{key}", (base or _Panel,), body)
        register("layout", key)(cls)
        return cls
    return deco


def _kind_size(ch, small):
    if lyrics.is_kanji(ch):
        return 1.0
    if lyrics.is_kata(ch):
        return 0.88
    if lyrics.is_latin(ch):
        return 0.8
    if lyrics.is_punct(ch):
        return 0.42
    return small * (0.8 if lyrics.is_small_kana(ch) else 1.0)


def _row_sized(ctx, idx, sizes, y=0.0, jitter=None, rot=None, gap=1.0):
    """Glyphs idx side by side with their own sizes, bottoms on one line."""
    w = sum(ctx.adv[i] * s for i, s in zip(idx, sizes)) * gap
    x, out = -w / 2, []
    for k, (i, s) in enumerate(zip(idx, sizes)):
        adv = ctx.adv[i] * s * gap
        out.append(G(i, x + adv / 2, y + (s - 1) * 0.45 + (jitter[k] if jitter else 0.0), s, rot[k] if rot else 0.0))
        x += adv
    return out


def _stack(rows, gap=0.25, align="c"):
    """Rows of glyph lists stacked from the top; each row is centred (or aligned) on x = 0."""
    out, y = [], 0.0
    for row in rows:
        if not row:
            continue
        h = max(g.s for g in row)
        y -= h / 2
        if align != "c":
            x0 = min(g.x - g.s / 2 for g in row)
            row = [g._replace(x=g.x - x0) for g in row] if align == "l" else row
        out += [g._replace(y=g.y + y) for g in row]
        y -= h / 2 + gap
    return out


# ---------------- core set (06_layouts.js) ----------------

@panel("mixed", "Big and Small", ("calm", "pop", "editorial", "emotional"), 1.0, (2, 16), scale=1.5,
       plan=lambda rng, ctx: {"small": rng.range(0.6, 0.72), "mode": rng.pick(["line", "stair", "line", "wave"]),
                              "rot": rng.range(2, 10), "j": [rng.range(-1, 1) for _ in ctx.text],
                              "r": [rng.range(-1, 1) for _ in ctx.text], "k": [rng() for _ in ctx.text]})
def mixed(ctx, p):
    vis = chars(ctx)
    rows = [vis] if len(vis) <= 9 else [vis[:math.ceil(len(vis) / 2)], vis[math.ceil(len(vis) / 2):]]
    out = []
    for row in rows:
        sizes = [_kind_size(ctx.text[i], p["small"] + p["k"][i] * 0.14) for i in row]
        jit = []
        for k, i in enumerate(row):
            dy = p["j"][i] * 0.06
            if p["mode"] == "stair":
                dy -= (k - (len(row) - 1) / 2) * 0.12
            if p["mode"] == "wave":
                dy += math.sin(k * 1.1) * 0.1
            jit.append(dy)
        out.append(_row_sized(ctx, row, sizes, jitter=jit, rot=[p["r"][i] * p["rot"] for i in row]))
    return _stack(out, 0.1)


@panel("columns", "Vertical Columns", ("calm", "editorial", "emotional", "glitch", "horror"), 0.9, (3, 18),
       vertical=True, max_h=40.0, plan=lambda rng, ctx: {"per": rng.int(3, 6)})
def columns(ctx, p):
    per = max(2, min(p["per"] + 1, math.ceil(n_vis(ctx.text) / math.ceil(n_vis(ctx.text) / 7))))
    out = []
    for c, (a, b) in enumerate(lines(ctx, per)):
        out += run_v(ctx, a, b, -c * 1.4, 0.0, top=True)                 # right to left
    return out


class _Ring(_Panel):
    max_w = max_h = 44.0

    def motion(self, ctx, params, t):
        t0 = ctx.span[0]
        return (t - t0) * params["speed"], np.zeros((len(t), 2))


@panel("ring", "Ring of Letters", ("pop", "graphic"), 0.9, (3, 16), base=_Ring,
       plan=lambda rng, ctx: {"speed": rng.range(4, 12) * rng.pick([1, -1]), "upright": rng.chance(0.3)})
def ring(ctx, p):
    vis = chars(ctx)
    R = max(1.3, len(vis) * 1.25 / (2 * math.pi))
    out = []
    for k, i in enumerate(vis):
        a = k / len(vis) * 360.0                                        # from the top, clockwise
        x, y = turn(0.0, R, a)
        out.append(G(i, x, y, 1.0, 0.0 if p["upright"] else a))
    return out



@panel("wave_path", "Wave Path", ("pop",), 0.9, (2, 16),
       plan=lambda rng, ctx: {"amp": rng.range(0.4, 0.8), "freq": rng.range(0.8, 1.6), "ph": rng.range(0, 6.28)})
def wave_path(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    span = n * 1.05
    path = lambda u: p["amp"] * math.sin(2 * math.pi * p["freq"] * u + p["ph"])
    out = []
    for k, i in enumerate(vis):
        x = (k - (n - 1) / 2) * 1.05
        u = x / max(span, 1e-6)
        slope = (path(u + 0.002) - path(u - 0.002)) / (0.004 * span)
        out.append(G(i, x, path(u), 1.0, -math.degrees(math.atan(slope))))
    return out


class _Huge(_Panel):
    max_w = 118.0
    max_h = 60.0
    scale = 3.0
    big = True

    def motion(self, ctx, params, t):
        t0, t1 = ctx.span
        u = np.clip((t - t0) / max(t1 - t0, 1e-3), 0, 1)
        off = np.zeros((len(t), 2))
        off[:, 0] = (0.5 - u) * params["_w"] * 0.16 * params["dir"]
        return np.zeros(len(t)), off


@panel("huge", "Bursting Past the View", ("glitch", "pop", "graphic", "emotional", "horror"), 0.8, (1, 8), base=_Huge,
       plan=lambda rng, ctx: {"dir": rng.pick([1, -1])})
def huge(ctx, p):
    rows = lines(ctx, math.ceil(n_vis(ctx.text) / 2)) if n_vis(ctx.text) >= 5 else [(0, len(ctx.text))]
    out = _stack([run_h(ctx, a, b, 0.0, 0.0) for a, b in rows], 0.0)
    p["_w"] = max(g.x for g in out) - min(g.x for g in out) + 1
    return out



@panel("labels", "Stuck-On Labels", ("pop", "graphic"), 0.8, (2, 16),
       plan=lambda rng, ctx: {"x": [rng.range(-1, 1) for _ in range(20)], "r": [rng.range(-1, 1) for _ in range(20)]})
def labels(ctx, p):
    us = units(ctx, min(5, max(2, n_vis(ctx.text) // 3)))
    return _stack([run_h(ctx, a, b, p["x"][j] * 1.2, 0.0, 1.0, p["r"][j] * 4) for j, (a, b) in enumerate(us)], 0.45)


@panel("diagonal", "Diagonal Band", ("pop", "graphic"), 0.9, (2, 16),
       plan=lambda rng, ctx: {"rot": -rng.range(10, 20) * rng.pick([1, 1, -1])})
def diagonal(ctx, p):
    return run_h(ctx, 0, len(ctx.text), 0.0, 0.0, 1.0, p["rot"])


@panel("circle_window", "Round Window", ("calm", "graphic", "editorial", "emotional"), 1.0, (3, 18))
def circle_window(ctx, p):
    n = n_vis(ctx.text)
    rows = lines(ctx, 3 if n <= 6 else 4 if n <= 12 else 5)
    return _stack([run_h(ctx, a, b, 0.0, 0.0) for a, b in rows], 0.15)


# ---------------- layoutsA ----------------

@panel("lower_third", "Lower Third", ("editorial", "calm", "emotional"), 1.0, (1, 24), elevation=-14.0, scale=0.75,
       keepable=False, plan=lambda rng, ctx: {"side": rng.pick([1, -1])})
def lower_third(ctx, p):
    return run_h(ctx, 0, len(ctx.text), 0.0, 0.0, align="l" if p["side"] < 0 else "r")


@panel("corners", "Opposite Corners", ("graphic", "editorial", "calm"), 1.0, (2, 18),
       plan=lambda rng, ctx: {"anti": rng.chance(0.4), "ratio": rng.pick([1.0, 0.7, 1.0])})
def corners(ctx, p):
    us = units(ctx, 2)
    wa = width(ctx, *us[0])
    wb = width(ctx, *us[-1]) * p["ratio"] if len(us) > 1 else 0.0
    W = max(wa, wb) * 1.7 + 1
    sx = -1 if p["anti"] else 1                                    # A top left, B bottom right (or the other way)
    a = run_h(ctx, *us[0], -sx * W / 2, 1.0, align="l" if sx > 0 else "r")
    b = run_h(ctx, *us[-1], sx * W / 2, -1.0, p["ratio"], align="r" if sx > 0 else "l") if len(us) > 1 else []
    return a + b


@panel("staircase", "Staircase", ("graphic", "pop", "editorial"), 1.0, (2, 18),
       plan=lambda rng, ctx: {"up": rng.chance(0.33), "shrink": rng.range(0.82, 0.9)})
def staircase(ctx, p):
    n = n_vis(ctx.text)
    us = [(i, i + 1) for i in chars(ctx)] if n <= 6 else units(ctx, 3 if n <= 10 else 4)
    out, x, y, s_prev, w_prev = [], 0.0, 0.0, None, 0.0
    for j, (a, b) in enumerate(us):
        s = p["shrink"] ** j
        if j:
            x += w_prev * 0.92 + s_prev * 0.14
            y += (s_prev + s) / 2 * 1.05 * (1 if p["up"] else -1)
        out += run_h(ctx, a, b, x, y, s, align="l")
        s_prev, w_prev = s, width(ctx, a, b) * s
    return out


@panel("zigzag", "Zigzag", ("pop", "graphic"), 0.9, (3, 16),
       plan=lambda rng, ctx: {"amp": rng.range(0.25, 0.5), "phase": rng.pick([1, -1])})
def zigzag(ctx, p):
    vis = chars(ctx)
    return [G(i, (k - (len(vis) - 1) / 2) * 1.08, (1 if k % 2 else -1) * p["phase"] * p["amp"]) for k, i in enumerate(vis)]


@panel("rainbow_arc", "Rainbow Arc", ("pop", "emotional", "graphic"), 0.9, (3, 16),
       plan=lambda rng, ctx: {"span": rng.range(100, 160)})
def rainbow_arc(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    span = min(p["span"], max(50.0, n * 30.0))
    dth = span / n * DEG
    R = 1.1 / dth
    out = []
    for k, i in enumerate(vis):
        a = -span / 2 + (k + 0.5) * span / n
        x, y = turn(0.0, R, a)
        out.append(G(i, x, y - R, 1.0, a))
    return out


@panel("spiral_in", "Spiral Inward", ("emotional", "graphic", "calm"), 0.8, (3, 16), max_w=44.0, max_h=44.0,
       plan=lambda rng, ctx: {"dir": rng.pick([1, -1])})
def spiral_in(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    R0, f = 1.0, 0.58
    c = min(0.42, 0.92 * math.sqrt(5.82 * f / n))
    out = []
    for k, i in enumerate(vis):
        r = R0 * (1 - f * k / n)                                   # inward; glyphs shrink with the radius
        a = p["dir"] * k * c * 1.08 / DEG
        x, y = turn(0.0, r, a)
        out.append(G(i, x, y, c * r, a))
    return [shrink(g, 1 / c) for g in out]


@panel("grid_cells", "Grid Cells", ("graphic", "editorial", "pop"), 1.0, (2, 18),
       plan=lambda rng, ctx: {"gap": rng.range(0.1, 0.3)})
def grid_cells(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    cols = max(2, math.ceil(math.sqrt(n * 1.8)))
    rows = math.ceil(n / cols)
    step = 1 + p["gap"]
    return [G(i, (k % cols - (cols - 1) / 2) * step, -(k // cols - (rows - 1) / 2) * step) for k, i in enumerate(vis)]


@panel("drop_cap", "Drop Cap", ("editorial", "emotional", "calm"), 1.0, (3, 24))
def drop_cap(ctx, p):
    vis = chars(ctx)
    cap = vis[0]
    rest = units_from(ctx, cap + 1, len(ctx.text), 2 if n_vis(ctx.text) <= 11 else 3)
    rows = _stack([run_h(ctx, a, b, 0.0, 0.0, align="l") for a, b in rest], 0.3, align="l")
    h = max(g.y for g in rows) - min(g.y for g in rows) + 1
    S = max(1.6, h)
    top = max(g.y for g in rows) + 0.5
    capg = G(cap, -S / 2 - 0.15, top - S / 2, S)
    return [capg] + rows


def units_from(ctx, a, b, k):
    sub = type("C", (), {})()
    sub.text, sub.chunks = ctx.text[a:b], [c for c in lyrics.chunk_text(ctx.text[a:b])]
    return [(a + x, a + y) for x, y in units(sub, k)] if n_vis(sub.text) else []


@panel("justified", "Justified Block", ("editorial", "calm", "emotional"), 0.8, (6, 30))
def justified(ctx, p):
    rows = [[i for i in range(a, b) if visible(ctx.text[i])] for a, b in lines(ctx, max(3, round(math.sqrt(n_vis(ctx.text) * 1.6))))]
    W = (max(len(r) for r in rows) - 1) * 1.04
    out = []
    for r, row in enumerate(rows):
        last = r == len(rows) - 1
        step = 1.04 if last or len(row) < 2 else max(1.04, W / (len(row) - 1))   # spread to the block's width
        out += [G(i, k * step, -r * 1.3) for k, i in enumerate(row)]
    return out


@panel("sideways", "Turned Sideways", ("editorial", "graphic", "pop"), 0.9, (3, 16), azimuth=24.0, big=True,
       max_w=40.0, max_h=60.0, plan=lambda rng, ctx: {"side": rng.pick([1, -1])})
def sideways(ctx, p):
    n = n_vis(ctx.text)
    rows = lines(ctx, math.ceil(n / 2)) if n > 6 else [(0, len(ctx.text))]
    rot = -90.0 if p["side"] < 0 else 90.0                         # reads upward on the left, downward on the right
    out = []
    for r, (a, b) in enumerate(rows):
        off = (r - (len(rows) - 1) / 2) * 1.05 * (1 if rot > 0 else -1)
        out += run_h(ctx, a, b, -off, 0.0, 1.0, rot)
    return out


@panel("edge_frame", "Around the Edge", ("graphic", "editorial", "glitch"), 0.8, (4, 24))
def edge_frame(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    w = max(2, math.ceil(n * 0.32))                                # cells along the top / bottom
    h = max(1, math.ceil((n - 2 * w) / 2))
    path = [(x, 0, 0) for x in range(w)] + [(w, -y, 90) for y in range(h)] + \
           [(w - x, -h, 180) for x in range(w)] + [(0, -h + y, 270) for y in range(h)]
    out = []
    for k, i in enumerate(vis):
        x, y, r = path[k % len(path)]
        out.append(G(i, x * 1.1, y * 1.1, 1.0, r))
    return out


@panel("perspective", "Receding Plane", ("graphic", "emotional", "glitch"), 0.9, (1, 18), tilt=58.0,
       elevation=-10.0, max_w=64.0, max_h=60.0, scale=1.3)
def perspective(ctx, p):
    n = n_vis(ctx.text)
    rows = lines(ctx, 8) if n > 10 else [(0, len(ctx.text))]
    return _stack([run_h(ctx, a, b, 0.0, 0.0) for a, b in rows], 0.2)


# ---------------- layoutsB ----------------

@panel("rain", "Letter Rain", ("glitch", "graphic", "emotional"), 0.8, (3, 16), max_h=40.0,
       plan=lambda rng, ctx: {"y": [rng.range(-1, 1) for _ in ctx.text]})
def rain(ctx, p):
    vis = chars(ctx)
    return [G(i, (k - (len(vis) - 1) / 2) * 1.3, p["y"][i] * 1.6) for k, i in enumerate(vis)]


@panel("hanging", "Hanging", ("pop", "calm", "emotional"), 0.9, (2, 16),
       plan=lambda rng, ctx: {"y": [rng() for _ in ctx.text], "r": [rng.range(-1, 1) for _ in ctx.text]})
def hanging(ctx, p):
    vis = chars(ctx)
    return [G(i, (k - (len(vis) - 1) / 2) * 1.2, -(0.3 + p["y"][i] * 1.2), 1.0, p["r"][i] * 6) for k, i in enumerate(vis)]


@panel("tunnel", "Tunnel", ("glitch", "graphic", "emotional"), 0.8, (3, 14), big=True, max_w=70.0, max_h=60.0,
       plan=lambda rng, ctx: {"dir": rng.pick([1, -1]), "a0": rng.range(-60, 60)})
def tunnel(ctx, p):
    vis = chars(ctx)
    out = []
    for k, i in enumerate(vis):
        a = p["a0"] + p["dir"] * k * 38.0
        dep = k * 2.2
        f = persp(ctx, dep) * (1 - 0.035 * k)                    # deeper glyphs look a little smaller and closer in
        x, y = turn(0.0, 2.4 * f, a)
        out.append(G(i, x, y, f, a, dep))
    return out


@panel("word_cloud", "Word Cloud", ("pop", "editorial", "graphic"), 0.9, (3, 24),
       plan=lambda rng, ctx: {"s": [rng.range(0.6, 1.5) for _ in range(12)], "x": [rng.range(-1, 1) for _ in range(12)]})
def word_cloud(ctx, p):
    us = units(ctx, min(7, max(2, n_vis(ctx.text) // 2)))
    rows, row, w = [], [], 0.0
    limit = max(4.0, math.sqrt(sum(width(ctx, a, b) for a, b in us)) * 2.2)
    for j, (a, b) in enumerate(us):
        s = p["s"][j]
        ww = width(ctx, a, b) * s
        if row and w + ww > limit:
            rows.append(row)
            row, w = [], 0.0
        row.append((a, b, s, w))
        w += ww + 0.4
    rows.append(row)
    out = []
    for r in rows:
        total = r[-1][3] + width(ctx, r[-1][0], r[-1][1]) * r[-1][2]
        line = []
        for a, b, s, x in r:
            line += run_h(ctx, a, b, x - total / 2, 0.0, s, align="l")
        out.append(line)
    return _stack(out, 0.2)


@panel("cross_bands", "Crossing Bands", ("graphic", "pop", "glitch"), 0.9, (4, 20))
def cross_bands(ctx, p):
    us = units(ctx, 2)
    a = run_h(ctx, *us[0], 0.0, 0.8, 1.0, -11.0)
    b = run_h(ctx, *us[-1], 0.0, -0.8, 1.0, 11.0, depth=0.6) if len(us) > 1 else []   # passes behind where they cross
    return a + b


@panel("stickers", "Sticker Bomb", ("pop", "graphic"), 0.9, (2, 18),
       plan=lambda rng, ctx: {"y": [rng.range(-1, 1) for _ in range(12)], "r": [rng.range(-1, 1) for _ in range(12)],
                              "s": [rng.range(0.8, 1.3) for _ in range(12)]})
def stickers(ctx, p):
    us = units(ctx, min(6, max(2, n_vis(ctx.text) // 2)))
    out, x = [], 0.0
    for j, (a, b) in enumerate(us):
        s = p["s"][j]
        w = width(ctx, a, b) * s
        out += run_h(ctx, a, b, x + w / 2, p["y"][j] * 0.6, s, p["r"][j] * 20, depth=j * 0.02)
        x += w + 0.3
    return out


class _Credits(_Panel):
    max_h = 40.0

    def motion(self, ctx, params, t):
        t0, t1 = ctx.span
        u = np.clip((t - t0) / max(t1 - t0, 1e-3), 0, 1)
        off = np.zeros((len(t), 2))
        off[:, 1] = (u - 0.5) * params["_h"] * 0.6
        return np.zeros(len(t)), off


@panel("credits", "End Credits", ("calm", "editorial", "emotional"), 0.9, (4, 30), base=_Credits)
def credits(ctx, p):
    out = _stack([run_h(ctx, a, b, 0.0, 0.0) for a, b in lines(ctx, 5)], 0.5)
    p["_h"] = max(g.y for g in out) - min(g.y for g in out) + 1
    return out



@panel("columns_big", "Big Column and Small", ("editorial", "calm", "emotional"), 0.9, (4, 20), vertical=True,
       max_h=40.0)
def columns_big(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 8 else 2)
    out = run_v(ctx, *us[0], 0.0, 0.0, 1.0, top=True)
    x = -1.2
    for a, b in us[1:]:
        out += run_v(ctx, a, b, x, -0.4, 0.6, top=True)
        x -= 0.85
    return out


@panel("circle_words", "Concentric Circles", ("graphic", "calm", "editorial"), 0.9, (4, 20), max_w=46.0, max_h=46.0)
def circle_words(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 8 else 2)
    out, R = [], 1.2
    for a, b in us:
        idx = [i for i in range(a, b) if visible(ctx.text[i])]
        R = max(R, len(idx) * 1.15 / math.pi)                    # the unit takes at most half a turn
        span = len(idx) * 1.15 / R / DEG
        for k, i in enumerate(idx):
            ang = -span / 2 + (k + 0.5) * span / len(idx)
            x, y = turn(0.0, R, ang)
            out.append(G(i, x, y, 1.0, ang))
        R += 1.6
    return out


@panel("depth_stack", "Stacked in Depth", ("graphic", "emotional", "glitch"), 0.9, (3, 20), max_h=40.0)
def depth_stack(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 8 else 2)
    out = []
    for j, (a, b) in enumerate(us):
        f = persp(ctx, j * 3.0)                                   # further back, bigger: the same apparent size
        out += run_h(ctx, a, b, (j - (len(us) - 1) / 2) * 0.8 * f, -j * 1.15 * f, f, depth=j * 3.0)
    return out


@panel("kanji_focus", "One Letter Big", ("emotional", "editorial", "calm"), 1.0, (2, 16))
def kanji_focus(ctx, p):
    ki = key_char(ctx)
    vis = chars(ctx)
    return _row_sized(ctx, vis, [2.4 if i == ki else 0.75 for i in vis])


@panel("mixed_dir", "Mixed Directions", ("editorial", "graphic"), 0.9, (4, 20))
def mixed_dir(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 6 else 2)
    out, x = [], 0.0
    for j, (a, b) in enumerate(us):
        if j % 2:
            out += run_v(ctx, a, b, x + 0.5, 0.5, top=True)
            x += 1.3
        else:
            w = width(ctx, a, b)
            out += run_h(ctx, a, b, x, 0.0, align="l")
            x += w + 0.3
    return out


@panel("cylinder", "Letter Drum", ("graphic", "calm", "emotional"), 0.9, (3, 16), keepable=True, max_w=56.0)
def cylinder(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    R = max(1.5, n * 1.05 / math.radians(110))                   # the text covers 110° of the drum
    out = []
    for k, i in enumerate(vis):
        a = (k - (n - 1) / 2) * 1.05 / R
        out.append(G(i, R * math.sin(a), 0.0, 1.0, 0.0, R * (1 - math.cos(a)), xform.yaw(a)))   # along the drum
    return out


# ---------------- layoutsC ----------------

@panel("headline", "Headline and Lead", ("editorial", "graphic", "calm"), 1.0, (4, 30))
def headline(ctx, p):
    us = units(ctx, 2)
    rows = [run_h(ctx, *us[0], 0.0, 0.0, 1.5, align="l")]
    if len(us) > 1:
        a, b = us[1]
        rows += [run_h(ctx, x, y, 0.0, 0.0, 0.62, align="l") for x, y in units_from(ctx, a, b, max(1, n_vis(ctx.text[a:b]) // 9 + 1))]
    return _stack(rows, 0.25, align="l")


@panel("poster", "Poster", ("graphic", "pop", "editorial"), 0.9, (4, 20),
       plan=lambda rng, ctx: {"rot": rng.range(-6, 6)})
def poster(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 6 else 2)
    W = max(width(ctx, a, b) for a, b in us)
    rows = []
    for j, (a, b) in enumerate(us):
        s = min(2.2, W / max(width(ctx, a, b), 1e-6)) * (1.0 if j % 2 == 0 else 0.85)
        rows.append(run_h(ctx, a, b, 0.0, 0.0, s))
    out = _stack(rows, 0.1)
    return [g._replace(x=turn(g.x, g.y, p["rot"])[0], y=turn(g.x, g.y, p["rot"])[1], rot=p["rot"]) for g in out]


@panel("swiss_grid", "Swiss Grid", ("graphic", "editorial", "calm"), 1.0, (4, 24))
def swiss_grid(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 6 else 2)
    out, y = [], 0.0
    for j, (a, b) in enumerate(us):
        s = 1.4 if j == 0 else 0.8
        out += run_h(ctx, a, b, j * 2.4, y, s, align="l")
        y -= s * 1.25
    return out


@panel("ransom", "Ransom Note", ("pop", "glitch", "graphic"), 0.8, (2, 18),
       plan=lambda rng, ctx: {"s": [rng.range(0.75, 1.35) for _ in ctx.text], "r": [rng.range(-1, 1) for _ in ctx.text],
                              "y": [rng.range(-1, 1) for _ in ctx.text]})
def ransom(ctx, p):
    vis = chars(ctx)
    return _row_sized(ctx, vis, [p["s"][i] for i in vis], jitter=[p["y"][i] * 0.15 for i in vis],
                      rot=[p["r"][i] * 12 for i in vis], gap=1.08)


@panel("route_map", "Route Map", ("graphic", "pop", "editorial"), 0.8, (4, 24))
def route_map(ctx, p):
    us = units(ctx, min(5, max(2, n_vis(ctx.text) // 2)))
    out, x = [], 0.0
    for j, (a, b) in enumerate(us):
        w = width(ctx, a, b) * 0.8
        out += run_h(ctx, a, b, x + w / 2, 0.75 if j % 2 == 0 else -0.75, 0.8)
        x += w * 0.75 + 0.4
    return out


# ---------------- layoutsD ----------------

@panel("accordion", "Accordion", ("pop", "graphic", "editorial"), 0.8, (3, 16), keepable=True,
       plan=lambda rng, ctx: {"a": rng.range(32, 46)})
def accordion(ctx, p):
    vis = chars(ctx)
    a = p["a"] * DEG
    step = math.cos(a)
    out = []
    for k, i in enumerate(vis):
        sgn = 1 if k % 2 else -1
        out.append(G(i, (k - (len(vis) - 1) / 2) * step * 1.05, 0.0, 1.0, 0.0, 0.5 * math.sin(a) * (k % 2),
                     xform.yaw(sgn * a)))
    return out


@panel("flag", "Waving Flag", ("emotional", "pop", "graphic"), 0.8, (3, 18), keepable=True,
       plan=lambda rng, ctx: {"amp": rng.range(0.35, 0.6), "len": rng.range(3.0, 5.0)})
def flag(ctx, p):
    vis = chars(ctx)
    out = []
    for k, i in enumerate(vis):
        x = (k - (len(vis) - 1) / 2) * 1.05
        ph = 2 * math.pi * x / p["len"]
        dep = p["amp"] * (math.sin(ph) + 1)
        slope = p["amp"] * math.cos(ph) * 2 * math.pi / p["len"]
        out.append(G(i, x, 0.15 * math.sin(ph + 1.0), 1.0, 0.0, dep, xform.yaw(math.atan(slope))))
    return out


@panel("ribbon", "Twisted Ribbon", ("pop", "emotional", "graphic"), 0.8, (3, 18), keepable=True,
       plan=lambda rng, ctx: {"tw": rng.range(30, 50), "ph": rng.range(0, 6.28)})
def ribbon(ctx, p):
    vis = chars(ctx)
    out = []
    for k, i in enumerate(vis):
        x = (k - (len(vis) - 1) / 2) * 1.05
        ang = p["tw"] * math.sin(x * 0.9 + p["ph"])
        out.append(G(i, x, 0.35 * math.sin(x * 0.6 + p["ph"]), 1.0, 0.0, 0.0, xform.pitch(-ang * DEG)))
    return out


@panel("pile", "Pile of Letters", ("pop", "emotional", "graphic"), 0.8, (3, 18), elevation=-8.0,
       plan=lambda rng, ctx: {"r": [rng.range(-1, 1) for _ in ctx.text], "x": [rng.range(-1, 1) for _ in ctx.text]})
def pile(ctx, p):
    vis = chars(ctx)
    rows, k, w = [], 0, 1
    while k < len(vis):
        rows.append(vis[k:k + w])
        k += w
        w += 1
    out = []
    for r, row in enumerate(rows):
        for c, i in enumerate(row):
            out.append(G(i, (c - (len(row) - 1) / 2) * 1.12 + p["x"][i] * 0.08, -r * 1.0, 1.0, p["r"][i] * 22))
    return out


@panel("fisheye", "Fisheye Lens", ("pop", "graphic", "glitch"), 0.8, (3, 16))
def fisheye(ctx, p):
    vis = chars(ctx)
    n = len(vis)
    sizes = [0.55 + 0.95 * math.cos(abs(k - (n - 1) / 2) / max((n - 1) / 2, 1) * math.pi / 2) ** 2 for k in range(n)]
    out = _row_sized(ctx, vis, sizes)
    return [g._replace(y=0.0) for g in out]


@panel("side_wall", "Wall in Perspective", ("graphic", "editorial", "emotional"), 0.8, (2, 18), azimuth=22.0,
       turn_board=-50.0, keepable=False, big=True, max_w=90.0, scale=1.3,
       plan=lambda rng, ctx: {"side": rng.pick([1, -1])})
def side_wall(ctx, p):
    n = n_vis(ctx.text)
    rows = lines(ctx, 8) if n > 10 else [(0, len(ctx.text))]
    return _stack([run_h(ctx, a, b, 0.0, 0.0) for a, b in rows], 0.2)


# ---------------- horror ----------------

@panel("hr_door_gap", "Through the Door Gap", ("horror", "editorial"), 0.9, (2, 12), group="horror", vertical=True,
       max_h=40.0, plan=lambda rng, ctx: {"x": [rng.range(-1, 1) for _ in ctx.text]})
def hr_door_gap(ctx, p):
    return [g._replace(x=g.x + p["x"][g.i] * 0.05) for g in run_v(ctx, 0, len(ctx.text), 0.0, 0.0)]


@panel("hr_scrawl", "Scrawled on the Wall", ("horror", "glitch"), 0.9, (2, 16), group="horror",
       plan=lambda rng, ctx: {"s": [rng.range(0.7, 1.5) for _ in ctx.text], "r": [rng.range(-1, 1) for _ in ctx.text],
                              "y": [rng.range(-1, 1) for _ in ctx.text], "g": [rng.range(0.85, 1.2) for _ in ctx.text]})
def hr_scrawl(ctx, p):
    vis = chars(ctx)
    out, x = [], 0.0
    for i in vis:
        s = p["s"][i]
        w = ctx.adv[i] * s * p["g"][i]
        out.append(G(i, x + w / 2, p["y"][i] * 0.3, s, p["r"][i] * 25))
        x += w
    return out


@panel("hr_ouija", "Spirit Board", ("horror",), 0.7, (3, 18), group="horror")
def hr_ouija(ctx, p):
    us = units(ctx, 2)
    out = []
    for j, (a, b) in enumerate(us):
        idx = [i for i in range(a, b) if visible(ctx.text[i])]
        R = max(3.0, len(idx) * 1.1 / math.radians(110))
        span = len(idx) * 1.1 / R / DEG
        for k, i in enumerate(idx):
            ang = -span / 2 + (k + 0.5) * span / len(idx)
            x, y = turn(0.0, R, ang)
            out.append(G(i, x, y - R - j * 1.4, 1.0, ang))
    return out


@panel("hr_wrong_one", "One Letter Wrong", ("horror", "editorial", "calm"), 0.9, (3, 18), keepable=True, group="horror",
       plan=lambda rng, ctx: {"pick": rng(), "how": rng.pick(["upside", "mirror"])})
def hr_wrong_one(ctx, p):
    out = run_h(ctx, 0, len(ctx.text), 0.0, 0.0)
    k = 1 + int(p["pick"] * (len(out) - 1)) if len(out) > 1 else 0
    k = min(k, len(out) - 1)
    g = out[k]
    out[k] = g._replace(rot=180.0) if p["how"] == "upside" else g._replace(extra=xform.yaw(math.pi))
    return out


@panel("hr_rising_dark", "Crawling Out of the Dark", ("horror", "emotional"), 0.8, (2, 16), group="horror",
       elevation=-16.0, keepable=False, plan=lambda rng, ctx: {"y": [rng() for _ in ctx.text]})
def hr_rising_dark(ctx, p):
    return [g._replace(y=-p["y"][g.i] * 0.5) for g in run_h(ctx, 0, len(ctx.text), 0.0, 0.0)]


# ---------------- kinetic ----------------

@panel("kn_slam_stack", "Slammed Stack", ("pop", "graphic"), 1.0, (3, 24), group="kinetic", max_h=40.0)
def kn_slam_stack(ctx, p):
    us = units(ctx, min(4, max(2, n_vis(ctx.text) // 3)))
    W = max(width(ctx, a, b) for a, b in us)
    return _stack([run_h(ctx, a, b, 0.0, 0.0, min(2.4, W / max(width(ctx, a, b), 1e-6))) for a, b in us], 0.08)


@panel("kn_quarter_turn", "Right-Angle Turns", ("pop", "graphic", "editorial"), 0.9, (4, 20), group="kinetic",
       max_h=44.0)
def kn_quarter_turn(ctx, p):
    us = units(ctx, min(4, max(2, n_vis(ctx.text) // 3)))
    out, x, y = [], 0.0, 0.0
    for j, (a, b) in enumerate(us):
        if j % 2 == 0:
            out += run_h(ctx, a, b, x, y, align="l")
            x += width(ctx, a, b) + 0.1
        else:
            col = run_v(ctx, a, b, x + 0.5, y - 0.6, top=True)
            out += col
            x += 1.1
            y = min(g.y for g in col) - 1.1
    return out


class _Seesaw(_Panel):
    def motion(self, ctx, params, t):
        t0 = ctx.span[0]
        return params["amp"] * np.sin((t - t0) * 2 * np.pi / params["period"]), np.zeros((len(t), 2))


@panel("kn_seesaw", "Seesaw", ("pop", "graphic"), 0.8, (2, 16), group="kinetic", base=_Seesaw,
       plan=lambda rng, ctx: {"amp": rng.range(5, 10), "period": rng.range(1.6, 2.6)})
def kn_seesaw(ctx, p):
    return run_h(ctx, 0, len(ctx.text), 0.0, 0.0)


@panel("kn_gears", "Gear Words", ("pop", "graphic"), 0.7, (4, 20), group="kinetic", max_w=56.0, max_h=44.0)
def kn_gears(ctx, p):
    us = units(ctx, 3 if n_vis(ctx.text) > 8 else 2)
    out, x = [], 0.0
    for j, (a, b) in enumerate(us):
        idx = [i for i in range(a, b) if visible(ctx.text[i])]
        R = max(1.0, len(idx) * 1.15 / (2 * math.pi) / 0.75)
        x += R
        for k, i in enumerate(idx):
            ang = k / len(idx) * 270 - 135 + (180 if j % 2 else 0)
            gx, gy = turn(0.0, R, ang)
            out.append(G(i, x + gx, gy + (0.4 if j % 2 else -0.4), 1.0, ang))
        x += R + 0.6
    return out


@panel("kn_pads", "Pad Grid", ("pop", "graphic", "glitch"), 0.8, (3, 24), group="kinetic")
def kn_pads(ctx, p):
    us = units(ctx, min(6, max(2, n_vis(ctx.text) // 2)))
    cols = 2 if len(us) <= 4 else 3
    cell = max(width(ctx, a, b) for a, b in us) + 0.8
    rows = math.ceil(len(us) / cols)
    out = []
    for j, (a, b) in enumerate(us):
        out += run_h(ctx, a, b, (j % cols - (cols - 1) / 2) * cell, -(j // cols - (rows - 1) / 2) * 1.8)
    return out


class _RhythmCuts(_Panel):
    keepable = False

    def shown(self, ctx, params, placement):
        us = params["_units"]
        starts = [ctx.char_times[min(a, len(ctx.char_times) - 1)] for a, _ in us]
        on = {}
        for j, (a, b) in enumerate(us):
            for i in range(a, b):
                on[i] = (-1e9 if j == 0 else starts[j], starts[j + 1] if j + 1 < len(us) else 1e9)
        return [on[g.char_index] for g in placement.glyphs]


@panel("kn_rhythm_cuts", "Word by Word Cuts", ("pop", "graphic", "glitch"), 0.9, (3, 24), group="kinetic",
       base=_RhythmCuts)
def kn_rhythm_cuts(ctx, p):
    us = units(ctx, min(5, max(2, n_vis(ctx.text) // 2)))
    p["_units"] = us
    return [g for a, b in us for g in run_h(ctx, a, b, 0.0, 0.0, 1.3)]

