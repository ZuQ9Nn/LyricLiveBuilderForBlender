"""Phase 0 prototype: Blender -> Unity conversion and the LLBM mesh binary writer.

Blender: right-handed, Z up, viewer faces +Y.  Unity: left-handed, Y up, faces +Z.
Swapping Y and Z is a reflection, which is exactly the handedness change, so:
  position (x, y, z) -> (x, z, y)
  quaternion (w, x, y, z) -> Unity (x, y, z, w) = (-x, -z, -y, w)
  triangle winding is reversed.
"""
import struct


def pos(v):
    return (v[0], v[2], v[1])


def quat(q):
    w, x, y, z = q
    return (-x, -z, -y, w)


def scale(s):
    return (s[0], s[2], s[1])


def write_llbm(positions, normals, indices):
    """positions/normals: lists of Blender-space tuples; indices: Blender winding triangles."""
    n_verts, n_idx = len(positions), len(indices)
    index32 = n_verts > 65535
    flags = 0b0001 | (0b1000 if index32 else 0)
    out = bytearray(b"LLBM")
    out += struct.pack("<HHIIHH", 1, flags, n_verts, n_idx, 0, 0)
    for p in positions:
        out += struct.pack("<3f", *pos(p))
    for n in normals:
        out += struct.pack("<3f", *pos(n))
    fmt = "<I" if index32 else "<H"
    for t in range(0, n_idx, 3):
        a, b, c = indices[t:t + 3]
        for i in (a, c, b):                      # reversed winding
            out += struct.pack(fmt, i)
    return bytes(out)


def mesh_to_llbm(me):
    """Blender mesh (evaluated, any polygons) -> LLBM bytes with flat-shaded split vertices."""
    me.calc_loop_triangles()
    positions, normals, indices = [], [], []
    for tri in me.loop_triangles:
        n = tuple(tri.normal)
        for vi in tri.vertices:
            indices.append(len(positions))
            positions.append(tuple(me.vertices[vi].co))
            normals.append(n)
    return write_llbm(positions, normals, indices)
