"""Line effects (spec §8.1, design §8.1): segments (and dots) made once per emitter and moved by a closed form
of time. The Blender preview evaluates state(); Unity's LyricLiveBuilder/Line shader repeats the same maths
from the baked mesh (export_unity: mesh_arrays) and the animated _LineState."""
import math

import numpy as np

from ..rng import h_np
from .particles import EYE

DRIFT_RATES = np.array([1.0, 1.3, 0.7])     # per Blender axis (the shader has them in Unity order)
FADE = 0.45                                 # links fade over this share of the link distance
MIN_ANGLE = 0.0015                          # rad: thinner lines are widened to this and dimmed by the ratio
MAX_POINTS, MAX_SEGMENTS = 60, 200          # budget (work procedure: plexus)
MIN_POINT_DISTANCE = 2.5                    # plexus points keep this far from the eye


def _u(seed, i, k):
    return h_np(seed, np.asarray(i), 0, k) / 4294967296.0


def is_lines(p):
    return p.get("emitter") == "lines"


def geometry(p, seed, colors):
    """Per-quad arrays (Blender space): a, b rest ends (Q, 3); pa, pb drift phases (Q, 3); sa, sb draw order;
    width; rgba (Q, 4) linear; soft (1 = soft across the width); dot (1 = a round dot at a)."""
    lines = p["lines"]
    cols = [tuple(c) for c in colors] or [(1.0, 1.0, 1.0)]
    if lines["kind"] == "ring":
        return _ring(lines, cols)
    if lines["kind"] == "plexus":
        return _plexus(lines, min(MAX_POINTS, int(p["max"])), seed, cols)
    raise KeyError(lines["kind"])


def _pack(a, b, pa, pb, sa, sb, width, rgba, soft, dot):
    f = lambda x: np.asarray(x, dtype=np.float64)
    return {"a": f(a), "b": f(b), "pa": f(pa), "pb": f(pb), "sa": f(sa), "sb": f(sb), "width": f(width),
            "rgba": f(rgba), "soft": f(soft), "dot": f(dot)}


def _ring(lines, cols):
    n = int(lines["segments"])
    th = -math.pi + 2 * math.pi * np.arange(n + 1) / n          # 0 = straight ahead (+y)
    ends = np.stack([np.sin(th) * lines["radius"], np.cos(th) * lines["radius"], np.full(n + 1, lines["height"])], axis=1)
    s = np.abs(th) / math.pi                                     # drawn from the front, both ways round
    out = []
    for width, alpha, soft, ci in lines["layers"]:
        c = cols[ci % len(cols)]
        out.append(_pack(ends[:-1], ends[1:], np.zeros((n, 3)), np.zeros((n, 3)), s[:-1], s[1:], np.full(n, width),
                         np.tile(list(c) + [alpha], (n, 1)), np.full(n, soft), np.zeros(n)))
    return {k: np.concatenate([o[k] for o in out]) for k in out[0]}


def _plexus(lines, count, seed, cols):
    (x0, x1), (y0, y1), (z0, z1) = lines["box"]
    pts, k = [], 0
    while len(pts) < count and k < count * 20:                   # deterministic rejection: not near the eye
        q = np.array([x0 + (x1 - x0) * _u(seed, k, 1), y0 + (y1 - y0) * _u(seed, k, 2), z0 + (z1 - z0) * _u(seed, k, 3)])
        k += 1
        if np.linalg.norm(q - EYE) >= MIN_POINT_DISTANCE:
            pts.append(q)
    pts = np.array(pts).reshape(-1, 3)
    n = len(pts)
    ph = np.stack([_u(seed, np.arange(n), 10 + j) * 2 * math.pi for j in range(3)], axis=1)
    reach = lines["link"] + 2 * lines["amp"]
    i, j = np.triu_indices(n, 1)
    d = np.linalg.norm(pts[i] - pts[j], axis=1)
    keep = np.argsort(d)[:MAX_SEGMENTS]
    keep = keep[d[keep] < reach]
    i, j = i[keep], j[keep]
    m = len(i)
    s_seg = _u(seed, np.arange(m), 20)
    s_dot = _u(seed, np.arange(n), 21)
    line_c, dot_c = cols[0], cols[1 % len(cols)]
    segs = _pack(pts[i], pts[j], ph[i], ph[j], s_seg, s_seg, np.full(m, lines["width"]),
                 np.tile(list(line_c) + [lines["alpha"]], (m, 1)), np.zeros(m), np.zeros(m))
    dots = _pack(pts, pts, ph, ph, s_dot, s_dot, np.full(n, lines["dot"]), np.tile(list(dot_c) + [1.0], (n, 1)),
                 np.zeros(n), np.ones(n))
    return {k: np.concatenate([segs[k], dots[k]]) for k in segs}


def progress(spec, t):
    """(draw, erase, tau) at time t: drawn from the start, erased from the end, tau = seconds since the start."""
    lines = spec["preset"]["lines"]
    draw_t = max(0.05, min(lines["draw"], (spec["end"] - spec["start"]) / 2))
    draw = float(np.clip((t - spec["start"]) / draw_t, 0, 1))
    erase = float(np.clip((t - spec["end"]) / lines["erase"], 0, 1))
    return draw, erase, float(t - spec["start"])


def state_keys(spec):
    """Keys of the line_state track (draw, erase, tau, 0): linear between them gives progress() exactly."""
    lines = spec["preset"]["lines"]
    s, e = spec["start"], spec["end"]
    draw_t = max(0.05, min(lines["draw"], (e - s) / 2))
    times = [s, s + draw_t, e, e + lines["erase"]]
    return times, [(0.0, 0.0, 0.0, 0.0), (1.0, 0.0, draw_t, 0.0), (1.0, 0.0, e - s, 0.0), (1.0, 1.0, e + lines["erase"] - s, 0.0)]


def positions(p, rest, phase, tau):
    lines = p["lines"]
    amp = lines.get("amp", 0.0)
    if not amp:
        return rest
    return rest + amp * np.sin(lines["speed"] * DRIFT_RATES * tau + phase)


def state(spec, geo, t, eye=EYE):
    """Quads facing the eye at time t -> (corners (Q*4, 3), rgba (Q*4, 4)) for the preview.
    Corner order per quad: a-side, a+side, b+side, b-side (dots: -right-up, +right-up, +right+up, -right+up)."""
    p = spec["preset"]
    draw, erase, tau = progress(spec, t)
    a = positions(p, geo["a"], geo["pa"], tau)
    b = positions(p, geo["b"], geo["pb"], tau)
    alpha = geo["rgba"][:, 3].copy()
    link = p["lines"].get("link", 0.0)
    if link:
        d = np.linalg.norm(b - a, axis=1)
        alpha *= np.clip((link - d) / (FADE * link), 0, 1)
    # the part with erase <= s <= draw (s runs linearly from sa to sb)
    sa, sb = geo["sa"], geo["sb"]
    ds = sb - sa
    flat = np.abs(ds) < 1e-9
    with np.errstate(divide="ignore", invalid="ignore"):
        ua = np.where(flat, 0.0, (np.where(ds > 0, erase, draw) - sa) / ds)
        ub = np.where(flat, 1.0, (np.where(ds > 0, draw, erase) - sa) / ds)
    u0, u1 = np.clip(ua, 0, 1), np.clip(ub, 0, 1)
    shown = np.where(flat, (sa >= erase) & (sa <= draw), u1 > u0)
    alpha *= shown
    a, b = a + (b - a) * u0[:, None], a + (b - a) * u1[:, None]
    mid = (a + b) / 2
    view = mid - eye
    dist = np.linalg.norm(view, axis=1)
    w = geo["width"].copy()
    thin = w < dist * MIN_ANGLE
    alpha = np.where(thin, alpha * w / np.maximum(dist * MIN_ANGLE, 1e-9), alpha)
    w = np.maximum(w, dist * MIN_ANGLE)
    side = np.cross(b - a, view)
    side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
    h = (w / 2)[:, None]
    seg = np.stack([a - side * h, a + side * h, b + side * h, b - side * h], axis=1)
    fwd = view / np.maximum(dist, 1e-9)[:, None]
    ref = np.where(np.abs(fwd[:, 2:3]) > 0.98, [[0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0]])     # straight up: another reference
    right = np.cross(fwd, ref)
    right /= np.maximum(np.linalg.norm(right, axis=1, keepdims=True), 1e-9)
    up = np.cross(right, fwd)
    dot = np.stack([a + (-right - up) * h, a + (right - up) * h, a + (right + up) * h, a + (-right + up) * h], axis=1)
    corners = np.where(geo["dot"][:, None, None] > 0.5, dot, seg).reshape(-1, 3)
    rgba = np.concatenate([geo["rgba"][:, :3], alpha[:, None]], axis=1)
    return corners, np.repeat(rgba, 4, axis=0)
