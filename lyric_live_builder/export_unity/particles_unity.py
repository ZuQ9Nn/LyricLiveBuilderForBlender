"""Emitter specs (core/parts/particles.py) -> Unity ParticleSystem descriptions (design §8.1).

Everything is decided here, in Unity space, so the C# side only copies fields into modules.
Unity simulates the particles itself: the result looks like the preview, it is not identical."""
import math

import numpy as np

from ..core.parts import particles as pts
from . import convert

EYE = [0.0, 1.5, 0.0]                      # Unity space
GRAVITY = 9.81


def _colors(spec):
    """Flat [r, g, b, a, r, g, b, a, ...] in sRGB (JsonUtility cannot read nested arrays)."""
    return [float(x) for c in spec["colors"] for x in convert.rgba(list(c) + [1.0])]


def _renderer(p):
    shape = p["shape"]
    if shape in pts.SHAPES_3D:
        return {"mode": "Mesh", "mesh": f"shape:{shape}", "meshes": [f"shape:{s}" for s in pts.shapes_of(p)],
                "tile": -1, "tileLast": -1, "blend": "alpha", "stretch": 0.0}
    first, last = pts.tile_range(p)
    return {"mode": "Stretch" if p.get("trail") else "Billboard", "mesh": "", "meshes": [], "tile": first,
            "tileLast": last, "blend": p.get("blend", "add"), "stretch": float(p.get("trail", 0.0))}


def _common(spec, p):
    life = [float(x) for x in p.get("life", (1.0, 1.0))]
    amp, freq = p.get("noise", 0.0), p.get("noise_freq", 0.3)
    return {
        "life": life, "speed": [0.0, 0.0], "size": [float(x) for x in p["size"]],
        "gravity": p.get("gravity", 0.0) / GRAVITY, "colors": _colors(spec),
        "fade": [float(x) for x in p.get("fade", (0.1, 0.3))], "sizeLife": p.get("size_life", "flat"),
        "spin": [float(x) for x in p.get("spin", (0.0, 0.0))],
        "noise": {"strength": amp * 2 * math.pi * freq, "frequency": 0.5, "scroll": freq},
        "velocity": {"x": [0.0, 0.0], "y": [0.0, 0.0], "z": [0.0, 0.0], "orbitalY": [0.0, 0.0]},
        "drag": 0.0, "renderer": _renderer(p), "sub": None, "burst": 0, "steps": None, "trail": _trail(p, life),
    }


def _trail(p, life):
    """Trail module: lifetime as a share of the particle's (mean) life, fixed width (tapers in C#)."""
    t = p.get("tail")
    if not t:
        return None
    return {"ratio": min(1.0, t["time"] / (sum(life) / 2)), "width": float(t["width"])}


UNITY_AXIS = {"x": 0, "y": 2, "z": 1}       # Blender axis -> Unity axis (convert.pos)


def _steps(p, system):
    """Velocity curves of one of the 3 stepped systems: per Unity axis, n segment values, low and high curve
    (flat [x0..xn-1, y0.., z0..]); a particle picks one speed per axis between the two curves."""
    axes = p["steps"]["axes"]
    n, v = len(axes), float(p["steps"]["speed"])
    lo, hi = [0.0] * (3 * n), [0.0] * (3 * n)
    for k, a in enumerate(axes):
        b = pts.STEP_AXES[system]["xyz".index(a)]
        j = UNITY_AXIS[b] * n + k
        lo[j], hi[j] = -v, v
    return {"n": n, "lo": lo, "hi": hi}


def line_key(node):
    return f"lines:{node}"


def line_mesh(geo):
    """Line effect quads -> (verts, faces, colours, uv4) for meshbin.encode. Per quad: (a, -1), (a, +1), (b, +1),
    (b, -1). POSITION = this end at rest; uv0 = other end (Unity) + side; uv1 = this end's drift phase (Unity
    axis order) + its draw order; uv2 = the other end's phase + width; uv3 = (soft, dot, end sign, 0)."""
    q = len(geo["width"])
    this_a = np.array([1, 1, 0, 0], dtype=bool)
    side = np.tile([-1.0, 1.0, 1.0, -1.0], q)
    end = np.tile([-1.0, -1.0, 1.0, 1.0], q)
    rep = lambda x: np.repeat(x, 4, axis=0)
    a_end = np.tile(this_a, q)[:, None]
    here, there = np.where(a_end, rep(geo["a"]), rep(geo["b"])), np.where(a_end, rep(geo["b"]), rep(geo["a"]))
    ph_here = np.where(a_end, rep(geo["pa"]), rep(geo["pb"]))
    ph_there = np.where(a_end, rep(geo["pb"]), rep(geo["pa"]))
    s_here = np.where(a_end[:, 0], rep(geo["sa"]), rep(geo["sb"]))
    uv0 = np.column_stack([convert.pos(there), side])
    uv1 = np.column_stack([convert.pos(ph_here), s_here])
    uv2 = np.column_stack([convert.pos(ph_there), rep(geo["width"])])
    uv3 = np.column_stack([rep(geo["soft"]), rep(geo["dot"]), end, np.zeros(4 * q)])
    faces = [(4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3) for k in range(q)]
    return here, faces, convert.rgba(rep(geo["rgba"])), [uv0, uv1, uv2, uv3]


def line_params(p):
    """Material values of a line effect (the same for the whole emitter): _Drift = amp, speed, link, min angle."""
    from ..core.parts import lines
    lp = p["lines"]
    return [{"name": "_Drift", "values": [float(lp.get("amp", 0.0)), float(lp.get("speed", 0.0)),
                                          float(lp.get("link", 0.0)), lines.MIN_ANGLE]}]


def _shape(kind, radius, r_in=0.0, position=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), random_dir=0.0):
    thick = 1.0 if radius <= 0 else max(0.0, min(1.0, (radius - r_in) / radius))
    return {"type": kind, "radius": float(radius), "thickness": thick, "position": [float(x) for x in position],
            "rotation": [float(x) for x in rotation], "randomDirection": float(random_dir)}


def continuous(spec, ratio=1.0):
    """Looping systems of a non-burst emitter (usually one; two for rings above and below).
    ratio: mobile share of the particle counts (spec §10.2)."""
    p = spec["preset"]
    r_in, r_out = p.get("radius", (1.0, 2.0))
    lo, hi = p.get("height", (0.0, 0.0))
    speed = [float(x) for x in p.get("speed", (0.0, 0.0))]
    kind = p["emitter"]
    d = _common(spec, p)
    d.update({"looping": True, "prewarm": bool(p.get("prewarm")), "rate": float(p["rate"]) * ratio,
              "max": max(1, int((spec["count"] or p["max"]) * ratio)), "duration": 5.0})
    out = []
    if kind == "sphere" and p.get("steps"):           # 3 systems with the axis order changed (design §8.1)
        d["shape"] = _shape("Sphere", r_out, r_in, EYE)
        for j in range(len(pts.STEP_AXES)):
            out.append(dict(d, steps=_steps(p, j), rate=d["rate"] / 3, max=max(1, d["max"] // 3)))
    elif kind in ("sphere", "sky_shell"):
        if kind == "sphere":
            d["shape"] = _shape("Sphere", r_out, r_in, EYE, random_dir=1.0)
            d["speed"] = speed
        else:
            d["shape"] = _shape("Hemisphere", r_out, r_in, EYE, rotation=(-90.0, 0.0, 0.0))
            if p.get("direction") == "fall":            # across the sky and slightly down
                v = speed[1]
                d["velocity"].update({"x": [-v, v], "z": [-v, v], "y": [-0.35 * v, -0.35 * v]})
        out.append(d)
    elif kind in ("sky_disc", "floor_disc"):
        d["shape"] = _shape("Circle", r_out, r_in, (0.0, (lo + hi) / 2, 0.0), rotation=(90.0, 0.0, 0.0))
        sign = -1.0 if p.get("direction") == "down" else 1.0
        d["velocity"]["y"] = sorted([sign * speed[0], sign * speed[1]])
        out.append(d)
    elif kind in ("ring", "point_orbit"):
        heights = (lo, hi) if p.get("height_pick") else ((lo + hi) / 2,)
        r_mid = (r_in + r_out) / 2
        a = math.radians(p.get("angle", 0.0))
        for h in heights:
            e = dict(d, velocity=dict(d["velocity"]))
            if kind == "ring":
                e["shape"] = _shape("Circle", r_out, r_in, (0.0, h, 0.0), rotation=(90.0, 0.0, 0.0))
            else:                                       # one point: emitted at a fixed rate -> evenly spaced
                e["shape"] = _shape("Sphere", 0.0, 0.0, convert.pos([math.sin(a) * r_in, math.cos(a) * r_in, h]))
            e["velocity"]["orbitalY"] = [speed[0] / r_mid, speed[1] / r_mid]       # radians per second
            e["velocity"]["y"] = [float(p.get("rise", 0.0))] * 2
            e["rate"] = d["rate"] / len(heights)
            e["max"] = max(1, d["max"] // len(heights))
            out.append(e)
    elif kind == "tunnel":
        d["shape"] = _shape("Circle", r_out, r_in, (0.0, EYE[1], 40.0))
        d["velocity"]["z"] = [-speed[1], -speed[0]]
        out.append(d)
    else:
        raise KeyError(kind)
    return out


def burst(spec, event, ratio=1.0):
    """One non-looping system for a burst event, placed at its origin (Unity space)."""
    p = spec["preset"]
    b = p["burst"]
    d = _common(spec, p)
    count = max(1, int(b["count"] * ratio))
    d.update({"looping": False, "prewarm": False, "rate": 0.0, "duration": 1.0, "burst": count,
              "max": count, "life": [float(x) for x in b["life"]], "speed": [float(x) for x in b["speed"]],
              "shape": _shape("Sphere", 0.05, 0.0, (0.0, 0.0, 0.0), random_dir=1.0), "drag": 1.5})
    if b.get("sub"):
        d["sub"] = {"count": int(b["sub"]["count"]), "speed": float(b["sub"]["speed"]), "life": float(b["sub"]["life"])}
        d["max"] = count
    origin = [float(x) for x in convert.pos(event["origin"])]
    span = b["life"][1] + (b["sub"]["life"] if b.get("sub") else 0.0)
    return d, origin, span
