"""Quaternion helpers on numpy arrays. Quaternions are (w, x, y, z); Blender axes (Z up, front +Y).

Frames used by the text parts:
- line / glyph local frame: x = along the text, z = up, -y = toward the viewer (the face).
"""
import numpy as np

IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def axis_angle(axis, angle):
    """axis: (3,) ; angle: scalar or array (...) -> (..., 4)."""
    axis = np.asarray(axis, dtype=np.float64)
    axis = axis / np.linalg.norm(axis)
    half = np.asarray(angle, dtype=np.float64)[..., None] * 0.5
    return np.concatenate([np.cos(half), np.sin(half) * axis], axis=-1)


def yaw(angle):
    """Rotation about +Z (positive turns +X toward +Y)."""
    return axis_angle((0, 0, 1), angle)


def pitch(angle):
    """Rotation about +X (positive turns +Y toward +Z)."""
    return axis_angle((1, 0, 0), angle)


def roll(angle):
    """Rotation about +Y (the axis from the viewer into the scene)."""
    return axis_angle((0, 1, 0), angle)


def mul(a, b):
    """Hamilton product a ⊗ b (apply b first, then a); broadcasts."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ], axis=-1)


def rotate(q, v):
    """Rotate vectors v (..., 3) by quaternions q (..., 4); broadcasts."""
    q, v = np.asarray(q, dtype=np.float64), np.asarray(v, dtype=np.float64)
    u, w = q[..., 1:], q[..., :1]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def facing(azimuth, elevation=0.0):
    """Rotation that turns a line's face (-y) back toward the eye from azimuth / elevation
    (azimuth 0 = straight ahead +Y, positive to the right +X; elevation positive = above)."""
    return mul(yaw(-np.asarray(azimuth)), pitch(np.asarray(elevation)))


def direction(azimuth, elevation=0.0):
    """Unit vector from the eye toward azimuth / elevation."""
    az, el = np.asarray(azimuth, dtype=np.float64), np.asarray(elevation, dtype=np.float64)
    return np.stack([np.sin(az) * np.cos(el), np.cos(az) * np.cos(el), np.sin(el)], axis=-1)


def normalize(q):
    q = np.asarray(q, dtype=np.float64)
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def continuous(q):
    """Flip signs along the last-but-one axis so consecutive keys take the short way (for linear keys)."""
    q = np.array(q, dtype=np.float64)
    dots = np.sum(q[..., 1:, :] * q[..., :-1, :], axis=-1)
    flips = np.cumprod(np.where(dots < 0, -1.0, 1.0), axis=-1)
    q[..., 1:, :] *= flips[..., None]
    return q
