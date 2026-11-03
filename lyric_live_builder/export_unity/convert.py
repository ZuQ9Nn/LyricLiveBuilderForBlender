"""Blender -> Unity conversion (design §9.4; settled by prototype S0-03).

Blender: right-handed, Z up, front +Y. Unity: left-handed, Y up, front +Z. Swapping Y and Z is a
reflection, which is exactly the change of handedness:
  position (x, y, z) -> (x, z, y); quaternion (w, x, y, z) -> Unity (x, y, z, w) = (-x, -z, -y, w);
  scale (x, y, z) -> (x, z, y); triangle winding is reversed.
Colours: the bake works in linear RGB; Unity colour properties take sRGB (also in Linear projects)."""
import numpy as np


def pos(v):
    v = np.asarray(v, dtype=np.float64)
    return v[..., [0, 2, 1]]


def quat(q):
    """(..., 4) Blender (w, x, y, z) -> Unity (x, y, z, w)."""
    q = np.asarray(q, dtype=np.float64)
    return np.stack([-q[..., 1], -q[..., 3], -q[..., 2], q[..., 0]], axis=-1)


def scale(s):
    return pos(s)


def srgb(c):
    """Linear -> sRGB, component-wise (alpha is passed through by the callers)."""
    c = np.clip(np.asarray(c, dtype=np.float64), 0.0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def rgba(c):
    """Linear (r, g, b[, a]) -> sRGB rgb with the alpha kept (..., 4)."""
    c = np.asarray(c, dtype=np.float64)
    a = c[..., 3:4] if c.shape[-1] == 4 else np.ones(c.shape[:-1] + (1,))
    return np.concatenate([srgb(c[..., :3]), a], axis=-1)


def triangles(faces):
    """Faces (tuples, any size) -> fan triangles in Unity winding (reversed)."""
    out = []
    for f in faces:
        for k in range(1, len(f) - 1):
            out.append((f[0], f[k + 1], f[k]))
    return np.array(out, dtype=np.int64).reshape(-1, 3)
