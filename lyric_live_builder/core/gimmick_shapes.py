"""Built-in gimmick shapes as numpy data (spec §8.3.1), all from primitives, no outside assets.

Every shape stands on z = 0, is 1 unit tall, centred on x and y, and faces -Y (a viewer at the eye
when its node turns toward the eye). Faces are n-gons wound counter-clockwise seen from outside."""
import math

import numpy as np

TAU = 2 * math.pi


def _merge(parts):
    verts, faces, base = [], [], 0
    for v, f in parts:
        verts.append(np.asarray(v, dtype=np.float64))
        faces += [tuple(i + base for i in face) for face in f]
        base += len(v)
    return np.concatenate(verts), faces


def _at(part, loc=(0, 0, 0), scale=1.0, rot_y=0.0, rot_x=0.0):
    """Scale, turn about Y then X, move."""
    v, f = part
    v = np.asarray(v, dtype=np.float64) * scale
    cy, sy, cx, sx = math.cos(rot_y), math.sin(rot_y), math.cos(rot_x), math.sin(rot_x)
    v = v @ np.array([[cy, 0, -sy], [0, 1, 0], [sy, 0, cy]]).T
    v = v @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]).T
    return v + loc, f


def box(sx, sy, sz, loc=(0, 0, 0)):
    x, y, z = sx / 2, sy / 2, sz / 2
    v = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    f = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return np.array(v, dtype=np.float64) + loc, f


def lathe(profile, segments=16):
    """Solid of revolution about Z: profile [(radius, z)] from bottom to top, radius 0 closes an end."""
    a = np.linspace(0, TAU, segments, endpoint=False)
    verts, rows = [], []
    for r, z in profile:
        if r <= 0:
            rows.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            rows.append(list(range(len(verts), len(verts) + segments)))
            verts += [(r * math.cos(x), r * math.sin(x), z) for x in a]
    faces = []
    for lo, hi in zip(rows, rows[1:]):
        if len(lo) == 1 and len(hi) == 1:
            continue
        for k in range(segments):
            n = (k + 1) % segments
            if len(lo) == 1:
                faces.append((lo[0], hi[n], hi[k]))
            elif len(hi) == 1:
                faces.append((lo[k], lo[n], hi[0]))
            else:
                faces.append((lo[k], lo[n], hi[n], hi[k]))
    if len(rows[0]) > 1:
        faces.append(tuple(reversed(rows[0])))
    if len(rows[-1]) > 1:
        faces.append(tuple(rows[-1]))
    return np.array(verts), faces


def plate(outline, depth, center=(0.0, 0.0)):
    """Outline (N, 2) in x, z (star-shaped around center), extruded along y with a fan on each side."""
    o = np.asarray(outline, dtype=np.float64)
    n = len(o)
    d = depth / 2
    v = [(x, -d, z) for x, z in o] + [(x, d, z) for x, z in o] + [(center[0], -d, center[1]), (center[0], d, center[1])]
    front, back = 2 * n, 2 * n + 1
    if _area(o) < 0:                                        # keep the front fan facing -Y
        f = [(front, (k + 1) % n, k) for k in range(n)]
        f += [(back, n + k, n + (k + 1) % n) for k in range(n)]
        f += [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    else:
        f = [(front, k, (k + 1) % n) for k in range(n)]
        f += [(back, n + (k + 1) % n, n + k) for k in range(n)]
        f += [((k + 1) % n, k, n + k, n + (k + 1) % n) for k in range(n)]
    return np.array(v), f


def _area(o):
    x, z = o[:, 0], o[:, 1]
    return 0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))


def strip(outer, inner, depth):
    """A band between two polylines (N, 2) in x, z (the crescent, the arch), extruded along y."""
    a, b = np.asarray(outer, dtype=np.float64), np.asarray(inner, dtype=np.float64)
    n, d = len(a), depth / 2
    v = np.concatenate([np.column_stack([p[:, 0], np.full(n, y), p[:, 1]]) for y in (-d, d) for p in (a, b)])
    f = []
    for k in range(n - 1):
        f += [(k, k + 1, n + k + 1, n + k)]                                  # front
        f += [(3 * n + k, 3 * n + k + 1, 2 * n + k + 1, 2 * n + k)]          # back
        f += [(2 * n + k, 2 * n + k + 1, k + 1, k)]                          # outer edge
        f += [(n + k, n + k + 1, 3 * n + k + 1, 3 * n + k)]                  # inner edge
    f += [(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1 + 0, 4 * n - 1, 3 * n - 1)[::-1]]
    return v, f


def torus(major, minor, segments=20, sides=8):
    """Ring around Y (facing the viewer)."""
    a, b = np.linspace(0, TAU, segments, endpoint=False), np.linspace(0, TAU, sides, endpoint=False)
    v = [((major + minor * math.cos(y)) * math.cos(x), minor * math.sin(y), (major + minor * math.cos(y)) * math.sin(x))
         for x in a for y in b]
    f = [(i * sides + j, i * sides + (j + 1) % sides, (i + 1) % segments * sides + (j + 1) % sides, (i + 1) % segments * sides + j)
         for i in range(segments) for j in range(sides)]
    return np.array(v), f


def ball(r=1.0, loc=(0, 0, 0), squash=(1.0, 1.0, 1.0), subdiv=2):
    from .meshes import icosphere                         # meshes.build() imports this module
    v, f = icosphere(subdiv, r)
    return v * squash + loc, f


def cylinder(r, h, loc=(0, 0, 0), segments=12, r_top=None):
    v, f = lathe([(r, 0.0), (r if r_top is None else r_top, h)] if r_top != 0 else [(r, 0.0), (0.0, h)], segments)
    return v + loc, f


def _star_outline(points, outer, inner):
    a = math.pi / 2 + np.arange(points * 2) * math.pi / points
    r = np.where(np.arange(points * 2) % 2 == 0, outer, inner)
    return np.stack([np.cos(a) * r, np.sin(a) * r], axis=1)


def _petal_outline(length, width, n=10):
    """A leaf from (0, 0) up to (0, length)."""
    t = np.linspace(0, 1, n)
    side = np.sin(math.pi * t) ** 0.8 * width
    right = np.stack([side, t * length], axis=1)
    left = np.stack([-side[-2:0:-1], (t * length)[-2:0:-1]], axis=1)
    return np.concatenate([right, left])


# ---------------- the shapes ----------------

def star():
    return plate(_star_outline(5, 0.5, 0.21), 0.14)


def moon():
    a = np.linspace(0.3 * math.pi, 1.7 * math.pi, 22)
    outer = np.stack([0.5 * np.cos(a), 0.5 * np.sin(a)], axis=1)
    inner = np.stack([0.16 + 0.42 * np.cos(a), 0.34 * np.sin(a)], axis=1) * [1, 1]
    inner[:, 1] *= np.abs(outer[:, 1]).max() / np.abs(inner[:, 1]).max()
    inner[0], inner[-1] = outer[0], outer[-1]
    return strip(outer, inner, 0.12)


def sun():
    return _merge([plate(_star_outline(12, 0.5, 0.36), 0.05), ball(0.3, squash=(1, 0.5, 1))])


def cloud():
    return _merge([ball(r, loc, (1, 0.8, 0.85), 1) for r, loc in
                   ((0.32, (0, 0, 0.05)), (0.24, (-0.3, 0, -0.05)), (0.26, (0.3, 0, -0.04)), (0.18, (-0.52, 0, -0.1)),
                    (0.18, (0.54, 0, -0.1)))])


def heart():
    t = np.linspace(0, TAU, 40, endpoint=False)
    x = 16 * np.sin(t) ** 3
    z = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    return plate(np.stack([x, z], axis=1) / 32, 0.22, center=(0.0, 0.05))


def flower():
    parts = [cylinder(0.035, 0.62, (0, 0, 0), 6)]
    parts += [_at(plate(_petal_outline(0.22, 0.1), 0.03), (0, 0, 0.72), rot_y=k * TAU / 7) for k in range(7)]
    parts += [ball(0.075, (0, -0.02, 0.72), subdiv=1)]
    parts += [_at(plate(_petal_outline(0.22, 0.07), 0.02), (0.02, 0, 0.2), rot_y=-1.1)]
    return _merge(parts)


def snow():
    parts = []
    for k in range(6):
        parts += [_at(box(0.05, 0.05, 0.5, (0, 0, 0.25)), rot_y=k * TAU / 6)]
        for sign in (-1, 1):
            parts += [_at(box(0.035, 0.05, 0.16, (0, 0, 0.08)), (0, 0, 0), rot_y=k * TAU / 6 + sign * 0.8)]
            arm = np.array([math.sin(k * TAU / 6), 0, math.cos(k * TAU / 6)]) * 0.3
            parts[-1] = (parts[-1][0] + arm, parts[-1][1])
    return _merge(parts)


def rain():
    t = np.linspace(0, 1, 9)
    profile = [(0.0, 0.0)] + [(0.3 * math.sin(math.pi * x) ** 0.9 * (1 - 0.65 * x) ** 0.4, x) for x in t[1:-1]] + [(0.0, 1.0)]
    return lathe(profile, 14)


def feather():
    return _merge([plate(_petal_outline(0.82, 0.16, 12), 0.02, center=(0.0, 0.4)), box(0.025, 0.03, 0.98, (0, 0, 0.49))])


def door():
    return _merge([box(0.58, 0.1, 1.0, (0, 0.02, 0.5)), box(0.46, 0.1, 0.92, (0, -0.02, 0.46)),
                   ball(0.03, (0.16, -0.09, 0.46), subdiv=1)])


def key():
    return _merge([_at(torus(0.16, 0.05, 16, 6), (0, 0, 0.8)), box(0.07, 0.05, 0.64, (0, 0, 0.32)),
                   box(0.16, 0.05, 0.06, (0.1, 0, 0.1)), box(0.12, 0.05, 0.06, (0.08, 0, 0.22))])


def clock():
    face = _at(cylinder(0.42, 0.08, (0, 0, -0.04), 28), (0, 0, 0.58), rot_x=math.pi / 2)
    rim = _at(torus(0.44, 0.05, 28, 6), (0, 0, 0.58))
    hands = [box(0.04, 0.03, 0.3, (0, -0.06, 0.72)), _at(box(0.04, 0.03, 0.22, (0, 0, 0.11)), (0, -0.07, 0.58), rot_y=2.1)]
    return _merge([face, rim, box(0.2, 0.2, 0.1, (0, 0, 0.05))] + hands)


def umbrella():
    canopy = lathe([(0.5, 0.56), (0.47, 0.62), (0.34, 0.74), (0.16, 0.83), (0.0, 0.88)], 8)
    return _merge([canopy, cylinder(0.018, 1.0, (0, 0, 0), 6), _at(torus(0.07, 0.018, 8, 4), (0.07, 0, 0.02))])


def note():
    return _merge([ball(0.15, (-0.1, 0, 0.13), (1.25, 0.6, 0.9)), box(0.04, 0.05, 0.84, (0.07, 0, 0.56)),
                   _at(plate(_petal_outline(0.34, 0.07), 0.04), (0.08, 0, 0.98), rot_y=2.3)])


def crown():
    parts = [lathe([(0.42, 0.0), (0.46, 0.34), (0.42, 0.34), (0.38, 0.0)], 20)]
    for k in range(6):
        a = k * TAU / 6 + 0.26
        loc = (0.43 * math.cos(a), 0.43 * math.sin(a), 0.3)
        parts += [cylinder(0.11, 0.62, loc, 5, 0.0), ball(0.05, (loc[0], loc[1], 0.96), subdiv=1)]
    return _merge(parts)


def gem():
    return lathe([(0.0, 0.0), (0.5, 0.58), (0.34, 1.0), (0.0, 1.0)], 8)


def candle():
    flame = lathe([(0.0, 0.0), (0.06, 0.05), (0.05, 0.12), (0.0, 0.24)], 8)
    return _merge([cylinder(0.11, 0.7), cylinder(0.008, 0.08, (0, 0, 0.7), 4), (flame[0] + (0, 0, 0.76), flame[1])])


def tree():
    return _merge([cylinder(0.08, 0.3), cylinder(0.42, 0.45, (0, 0, 0.22), 12, 0.0), cylinder(0.34, 0.4, (0, 0, 0.44), 12, 0.0),
                   cylinder(0.25, 0.36, (0, 0, 0.64), 12, 0.0)])


def pillar():
    return lathe([(0.0, 0.0), (0.24, 0.0), (0.24, 0.06), (0.16, 0.1), (0.14, 0.9), (0.2, 0.95), (0.24, 0.95), (0.24, 1.0), (0.0, 1.0)], 14)


def arch():
    a = np.linspace(0, math.pi, 18)
    return _merge([strip(np.stack([0.5 * np.cos(a), 0.5 + 0.5 * np.sin(a)], axis=1),
                         np.stack([0.34 * np.cos(a), 0.5 + 0.36 * np.sin(a)], axis=1), 0.2),
                   box(0.16, 0.2, 0.5, (-0.42, 0, 0.25)), box(0.16, 0.2, 0.5, (0.42, 0, 0.25))])


def gift():
    return _merge([box(0.8, 0.8, 0.72, (0, 0, 0.36)), box(0.86, 0.86, 0.1, (0, 0, 0.74)), box(0.12, 0.84, 0.74, (0, 0, 0.37)),
                   box(0.84, 0.12, 0.74, (0, 0, 0.37)), ball(0.1, (-0.1, 0, 0.9), (1.2, 0.5, 0.8), 1), ball(0.1, (0.1, 0, 0.9), (1.2, 0.5, 0.8), 1)])


def ring():
    return _merge([_at(torus(0.34, 0.05, 24, 6), (0, 0, 0.38)), gem_on_ring()])


def gem_on_ring():
    v, f = lathe([(0.0, 0.0), (0.16, 0.14), (0.1, 0.24), (0.0, 0.24)], 8)
    return v + (0, 0, 0.72), f


def bell():
    return _merge([lathe([(0.46, 0.0), (0.4, 0.08), (0.28, 0.3), (0.24, 0.6), (0.16, 0.82), (0.0, 0.88)], 16),
                   ball(0.08, (0, 0, 0.0), subdiv=1), _at(torus(0.07, 0.02, 8, 4), (0, 0, 0.93))])


def leaf():
    return _merge([plate(_petal_outline(0.86, 0.3, 12), 0.03, center=(0.0, 0.4)), box(0.03, 0.05, 1.0, (0, 0, 0.5))])


def house():
    roof = plate(np.array([(-0.54, 0.56), (0.54, 0.56), (0.0, 1.0)]), 0.76, center=(0.0, 0.7))
    return _merge([box(0.8, 0.7, 0.58, (0, 0, 0.29)), roof, box(0.18, 0.04, 0.32, (0, -0.35, 0.16)), box(0.1, 0.1, 0.3, (0.24, 0, 0.84))])


def wall_panel():
    """One side of the opening box: 1 × 1, hinged on its lower edge."""
    return box(1.0, 0.04, 1.0, (0, 0, 0.5))


def disc_plate():
    """The floor plate that flips, the emblem's pedestal: radius 1."""
    return lathe([(0.0, -0.04), (1.0, -0.04), (1.0, 0.0), (0.0, 0.0)], 32)


def bar():
    """A spectrum bar, 1 × 1 × 1 on the floor."""
    return box(1.0, 1.0, 1.0, (0, 0, 0.5))


# tag -> (name, build, colour, floats in the air, size relative to the standard visual angle)
SHAPES = {
    "star": ("Star Shape", star, "#FFD84A", True, 0.8), "moon": ("Moon", moon, "#F2E6A8", True, 0.9),
    "sun": ("Sun", sun, "#FFB02E", True, 1.0), "cloud": ("Cloud", cloud, "#E8EEF6", True, 0.7),
    "heart": ("Heart", heart, "#F0506E", True, 0.8), "flower": ("Flower", flower, "#F58FB5", False, 0.9),
    "snow": ("Snow Crystal", snow, "#BFE6FF", True, 0.8), "rain": ("Raindrop", rain, "#5CB3F0", True, 0.6),
    "feather": ("Feather Shape", feather, "#F4F1E8", True, 0.8), "door": ("Door", door, "#9A6A42", False, 1.3),
    "key": ("Door Key", key, "#E6C04A", True, 0.8), "clock": ("Clock", clock, "#D8DCE4", False, 1.0),
    "umbrella": ("Umbrella", umbrella, "#D84A5C", False, 1.1), "note": ("Music Note", note, "#8C7CF0", True, 0.8),
    "crown": ("Crown", crown, "#F2C53D", True, 0.6), "gem": ("Gem", gem, "#59D6E8", True, 0.6),
    "candle": ("Candle", candle, "#F4E8D0", False, 0.7), "tree": ("Tree", tree, "#4FA868", False, 1.4),
    "pillar": ("Pillar", pillar, "#CFC9BC", False, 1.5), "arch": ("Arch", arch, "#C9B8A0", False, 1.4),
    "box": ("Gift Box", gift, "#E86A5C", False, 0.7), "ring": ("Finger Ring", ring, "#E6C04A", True, 0.6),
    "bell": ("Bell", bell, "#E8B83C", True, 0.7), "leaf": ("Leaf", leaf, "#6CBF6A", True, 0.7),
    "house": ("House", house, "#D9B48F", False, 1.2),
}
PARTS = {"panel": wall_panel, "plate": disc_plate, "bar": bar}


def _standard(v, f):
    """Stand it on z = 0, 1 unit tall, centred on x and y."""
    lo, hi = v.min(axis=0), v.max(axis=0)
    v = (v - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) / max(hi[2] - lo[2], 1e-9)
    return v, f


def build(key_):
    if key_ in PARTS:
        return PARTS[key_]()
    return _standard(*SHAPES[key_][1]())
