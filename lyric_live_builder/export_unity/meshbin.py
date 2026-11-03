"""LLBM meshes packed into meshes.bin (design §9.3). Input is Blender-space data; output is Unity space."""
import struct

import numpy as np

from . import convert

FLAG_NORMALS, FLAG_UV, FLAG_COLORS, FLAG_INDEX32 = 1, 2, 4, 8


def _face_normals(v, tris):
    n = np.cross(v[tris[:, 1]] - v[tris[:, 0]], v[tris[:, 2]] - v[tris[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def encode(verts, faces, flat=False, colors=None):
    """verts (V, 3) and faces (tuples) in Blender space -> LLBM bytes with normals.
    flat: split vertices per triangle corner so every face keeps its own normal (3D letters).
    colors: optional (V, 4) sRGB 0..1 per vertex (merged line meshes)."""
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    col = None if colors is None else np.asarray(colors, dtype=np.float64).reshape(-1, 4)
    tris = np.array([(f[0], f[k], f[k + 1]) for f in faces for k in range(1, len(f) - 1)], dtype=np.int64).reshape(-1, 3)
    fn = _face_normals(v, tris) if len(tris) else np.zeros((0, 3))
    if flat:
        if col is not None:
            col = col[tris.reshape(-1)]
        v = v[tris.reshape(-1)]
        n = np.repeat(fn, 3, axis=0)
        tris = np.arange(len(v)).reshape(-1, 3)
    else:
        n = np.zeros_like(v)
        for k in range(3):
            np.add.at(n, tris[:, k], fn)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    index32 = len(v) > 65535
    flags = FLAG_NORMALS | (FLAG_INDEX32 if index32 else 0) | (FLAG_COLORS if col is not None else 0)
    idx = tris[:, [0, 2, 1]].reshape(-1)                  # reflection: reverse the winding
    head = b"LLBM" + struct.pack("<HHIIHH", 1, flags, len(v), len(idx), 0, 0)
    body = convert.pos(v).astype("<f4").tobytes() + convert.pos(n).astype("<f4").tobytes()
    if col is not None:
        body += np.clip(np.round(col * 255), 0, 255).astype(np.uint8).tobytes()
    return head + body + idx.astype("<u4" if index32 else "<u2").tobytes()


def decode(data, offset=0):
    """LLBM bytes -> (positions, normals, indices, colours or None) in Unity space (for tests)."""
    if data[offset:offset + 4] != b"LLBM":
        raise ValueError("not an LLBM mesh")
    _, flags, nv, ni, _, _ = struct.unpack_from("<HHIIHH", data, offset + 4)
    p = offset + 20
    pos = np.frombuffer(data, "<f4", nv * 3, p).reshape(-1, 3)
    p += nv * 12
    nrm = None
    if flags & FLAG_NORMALS:
        nrm = np.frombuffer(data, "<f4", nv * 3, p).reshape(-1, 3)
        p += nv * 12
    if flags & FLAG_UV:
        p += nv * 8
    col = None
    if flags & FLAG_COLORS:
        col = np.frombuffer(data, np.uint8, nv * 4, p).reshape(-1, 4) / 255.0
        p += nv * 4
    idx = np.frombuffer(data, "<u4" if flags & FLAG_INDEX32 else "<u2", ni, p)
    return pos, nrm, idx, col


class Pack:
    """Meshes appended into one buffer; each keeps (offset, length) for the manifest."""

    def __init__(self):
        self.parts, self.size, self.entries = [], 0, []

    def add(self, key, data):
        self.entries.append({"key": key, "offset": self.size, "length": len(data)})
        self.parts.append(data)
        self.size += len(data)

    def bytes(self):
        return b"".join(self.parts)
