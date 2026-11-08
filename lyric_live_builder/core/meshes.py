"""Built-in meshes as numpy data (verts (V, 3), faces [tuple]) shared by the preview and the export.

Coordinates are Blender's (Z up, front +Y). Faces wind counter-clockwise seen from outside,
except the dome, which faces inward (the audience is inside it)."""
import math

import numpy as np

from . import gimmick_shapes
from .rng import h_np


def icosphere(subdiv=1, radius=1.0):
    t = (1 + math.sqrt(5)) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, dtype=np.float64) / np.linalg.norm(p) for p in v]
    for _ in range(subdiv):
        mid, nf = {}, []

        def m(a, b):
            k = (min(a, b), max(a, b))
            if k not in mid:
                p = verts[a] + verts[b]
                verts.append(p / np.linalg.norm(p))
                mid[k] = len(verts) - 1
            return mid[k]
        for a, b, c in f:
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    return np.array(verts) * radius, f


def dome(radius=60.0, subdiv=3):
    """Inward-facing icosphere (design §8.2)."""
    v, f = icosphere(subdiv, radius)
    return v, [(a, c, b) for a, b, c in f]


def disc(segments=32, radius=1.0):
    """Disc in the XZ plane facing -Y (toward a viewer at the origin when placed at +Y)."""
    a = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    v = np.concatenate([[[0.0, 0.0, 0.0]], np.stack([np.cos(a), np.zeros(segments), np.sin(a)], axis=1) * radius])
    return v, [(0, 1 + k, 1 + (k + 1) % segments) for k in range(segments)]


def ring_band(profile, radius):
    """A vertical band around the origin, facing inward: profile (N,) heights at evenly spaced azimuths."""
    n = len(profile)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y = np.sin(a) * radius, np.cos(a) * radius
    bottom = np.stack([x, y, np.zeros(n)], axis=1)
    top = np.stack([x, y, np.asarray(profile, dtype=np.float64)], axis=1)
    f = [(k, (k + 1) % n, n + (k + 1) % n, n + k) for k in range(n)]
    return np.concatenate([bottom, top]), f


def mountains(radius=48.0, seed=3, n=180):
    """Jagged ridge line: the sum of a few octaves of hashed bumps."""
    k = np.arange(n)
    hgt = np.zeros(n)
    for octave, (period, amp) in enumerate(((30, 6.0), (12, 2.6), (5, 1.0))):
        ph = h_np(seed, octave, k // period) / 4294967296.0
        nx = h_np(seed, octave, k // period + 1) / 4294967296.0
        u = (k % period) / period
        u = u * u * (3 - 2 * u)
        hgt += amp * (ph + (nx - ph) * u)
    return ring_band(1.5 + hgt, radius)


def city(radius=40.0, seed=5, n=120):
    """Skyline of flat facades: stepped heights per block."""
    k = np.arange(n)
    block = k // 3
    hgt = 2.0 + 10.0 * (h_np(seed, block) / 4294967296.0) ** 2
    return ring_band(hgt, radius)


def water(radius=55.0, segments=64, z=-0.6):
    """Horizontal disc below the audience (the sea / horizon), facing up."""
    a = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    v = np.concatenate([[[0.0, 0.0, z]], np.stack([np.cos(a) * radius, np.sin(a) * radius, np.full(segments, z)], axis=1)])
    return v, [(0, 1 + k, 1 + (k + 1) % segments) for k in range(segments)]


def _prism(sides, r=0.5, height=1.0):
    a = np.linspace(0, 2 * math.pi, sides, endpoint=False)
    ring = np.stack([np.cos(a) * r, np.sin(a) * r, np.zeros(sides)], axis=1)
    v = np.concatenate([ring + [0, 0, -height / 2], ring + [0, 0, height / 2]])
    f = [tuple(range(sides - 1, -1, -1)), tuple(range(sides, 2 * sides))]
    f += [(k, (k + 1) % sides, sides + (k + 1) % sides, sides + k) for k in range(sides)]
    return v, f


def particle_shape(kind):
    """3D particle shapes, about 1 unit across (spec §8.1)."""
    if kind == "cube":
        return _prism(4, r=0.7071, height=1.0)
    if kind == "hexprism":
        return _prism(6, r=0.5, height=0.6)
    if kind == "octahedron":
        v = np.array([(0.5, 0, 0), (-0.5, 0, 0), (0, 0.5, 0), (0, -0.5, 0), (0, 0, 0.5), (0, 0, -0.5)])
        return v, [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
    if kind == "icosahedron":
        return icosphere(0, 0.5)
    if kind == "shard":
        v = np.array([(-0.5, -0.04, -0.3), (0.45, -0.04, -0.2), (0.1, -0.04, 0.5),
                      (-0.5, 0.04, -0.3), (0.45, 0.04, -0.2), (0.1, 0.04, 0.5)])
        return v, [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)]
    if kind == "tetra":
        v = np.array([(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)], dtype=np.float64) * 0.35
        return v, [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)]
    raise KeyError(kind)


def quad():
    """Unit billboard in the XZ plane facing -Y, UV 0..1."""
    v = np.array([(-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (-0.5, 0, 0.5)])
    return v, [(0, 1, 2, 3)]


def build(key):
    """MeshSource key -> (verts, faces) for the built-in kinds."""
    kind, _, arg = key.partition(":")
    if kind == "dome":
        return dome()
    if kind == "far":
        return {"moon": lambda: disc(40), "sun": lambda: disc(40), "mountains": mountains,
                "city": city, "water": water}[arg]()
    if kind == "orb":
        return icosphere(2, 0.5)
    if kind == "quad":
        return quad()
    if kind == "shape":
        return particle_shape(arg)
    if kind == "gimmick":
        return gimmick_shapes.build(arg)
    raise KeyError(key)
