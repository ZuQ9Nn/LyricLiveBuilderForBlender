"""Particle texture atlas drawn from distance fields (spec §8.1, design §8.1): 4×4 tiles, white RGB
with the shape in alpha. Shared by the preview and the Unity export; no image assets are used."""
import math
import struct
import zlib

import numpy as np

from .parts.particles import SHAPES_2D

GRID = 4


def _poly(x, y, n, r, rot=0.0):
    """Signed distance (negative inside) to a regular n-gon of circumradius r."""
    a = np.arctan2(y, x) - rot
    seg = 2 * math.pi / n
    ang = (a % seg) - seg / 2
    return np.hypot(x, y) * np.cos(ang) - r * math.cos(math.pi / n)


def _segment(x, y, ax, ay, bx, by):
    px, py, dx, dy = x - ax, y - ay, bx - ax, by - ay
    t = np.clip((px * dx + py * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - dx * t, py - dy * t)


def _heart(x, y):
    # heart distance (after Inigo Quilez, MIT), scaled to the tile
    k = 0.62
    px, py = np.abs(x) * k, (y + 0.85) * k
    top = np.hypot(px - 0.25, py - 0.75) - math.sqrt(2) / 4
    m = 0.5 * np.maximum(px + py, 0)
    low = np.sqrt(np.minimum((px) ** 2 + (py - 1) ** 2, (px - m) ** 2 + (py - m) ** 2)) * np.sign(px - py)
    return np.where(py + px > 1, top, low) / k


def _shape(name, x, y, px):
    """Coverage 0..1 of one shape on a grid x, y in -1..1; px = one pixel in those units."""
    r = np.hypot(x, y)

    def fill(d):
        return np.clip(0.5 - d / (1.5 * px), 0, 1)
    if name == "circle_dot":
        return fill(r - 0.8)
    if name == "soft_dot":
        return np.clip(np.exp(-r * r * 5.0) - 0.007, 0, 1)
    if name == "triangle":
        return fill(_poly(x, y + 0.12, 3, 0.85, math.pi / 2))
    if name == "square":
        return fill(np.maximum(np.abs(x), np.abs(y)) - 0.68)
    if name == "cross":
        d = np.minimum(_segment(x, y, -0.6, -0.6, 0.6, 0.6), _segment(x, y, -0.6, 0.6, 0.6, -0.6))
        return fill(d - 0.13)
    if name == "hexagon":
        return fill(_poly(x, y, 6, 0.85))
    if name == "octagon":
        return fill(_poly(x, y, 8, 0.85, math.pi / 8))
    if name == "bubble":
        rim = fill(np.abs(r - 0.78) - 0.06)
        shine = fill(np.hypot(x + 0.32, y - 0.35) - 0.14)
        return np.clip(np.maximum(rim, shine) + 0.18 * fill(r - 0.78), 0, 1)
    if name == "star":
        a = np.arctan2(y, x) - math.pi / 2
        seg = 2 * math.pi / 5
        f = np.abs((a % seg) / seg * 2 - 1)                  # 1 at the points, 0 between
        return fill(r - (0.38 + 0.5 * f ** 1.6))
    if name == "sparkle":
        streak = np.exp(-np.abs(x) * 9) * np.exp(-y * y * 2.5) + np.exp(-np.abs(y) * 9) * np.exp(-x * x * 2.5)
        return np.clip(streak + np.exp(-r * r * 18), 0, 1)
    if name == "petal":
        # two overlapping circles make a pointed leaf; tilted
        c, s = math.cos(0.5), math.sin(0.5)
        u, v = x * c - y * s, x * s + y * c
        return fill(np.maximum(np.hypot(u - 0.45, v) - 0.95, np.hypot(u + 0.45, v) - 0.95))
    if name == "heart":
        return fill(_heart(x, y))
    if name == "note":
        head = np.hypot((x + 0.22) * 1.0, (y + 0.5) * 1.45) - 0.3
        stem = np.maximum(np.abs(x - 0.06) - 0.06, np.abs(y - 0.12) - 0.66)
        flag = _segment(x, y, 0.06, 0.76, 0.48, 0.32) - 0.09
        return fill(np.minimum(np.minimum(head, stem), flag))
    if name == "snowflake":
        d = np.full(x.shape, 9.0)
        for k in range(6):
            a = k * math.pi / 3
            ca, sa = math.cos(a), math.sin(a)
            d = np.minimum(d, _segment(x, y, 0, 0, 0.85 * ca, 0.85 * sa))
            for t, l in ((0.45, 0.25), (0.65, 0.17)):
                bx, by = t * ca, t * sa
                for side in (1, -1):
                    b = a + side * math.pi / 3
                    d = np.minimum(d, _segment(x, y, bx, by, bx + l * math.cos(b), by + l * math.sin(b)))
        return fill(d - 0.055)
    if name == "ring":
        return fill(np.abs(r - 0.7) - 0.11)
    raise KeyError(name)


def draw(size=1024):
    """(size, size, 4) float32 RGBA, row 0 at the top; tile k at row k // 4, column k % 4."""
    tile = size // GRID
    c = (np.arange(tile) + 0.5) / tile * 2 - 1
    x, y = np.meshgrid(c, -c)
    out = np.zeros((size, size, 4), dtype=np.float32)
    out[..., :3] = 1.0
    for k, name in enumerate(SHAPES_2D):
        r0, c0 = (k // GRID) * tile, (k % GRID) * tile
        out[r0:r0 + tile, c0:c0 + tile, 3] = _shape(name, x / 0.92, y / 0.92, 2.0 / tile / 0.92)
    return out


def tile_uv(k):
    """(u0, v0, u1, v1) of tile k in Blender / Unity UVs (v up, image bottom = 0)."""
    row, col = k // GRID, k % GRID
    return col / GRID, 1 - (row + 1) / GRID, (col + 1) / GRID, 1 - row / GRID


def png_decode(data):
    """(h, w, 4) uint8 of a PNG written by png_bytes (8-bit RGBA, no filters); ValueError for anything else."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, size = 8, [], None
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            if (depth, ctype) != (8, 6):
                raise ValueError("only 8-bit RGBA")
            size = (h, w)
        elif tag == b"IDAT":
            idat.append(body)
        pos += 12 + n
    h, w = size
    rows = np.frombuffer(zlib.decompress(b"".join(idat)), np.uint8).reshape(h, 1 + w * 4)
    if rows[:, 0].any():
        raise ValueError("filtered rows are not read")
    return rows[:, 1:].reshape(h, w, 4)


def png_bytes(rgba):
    """Minimal PNG (8-bit RGBA) writer with the standard library."""
    h, w = rgba.shape[:2]
    raw = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
    rows = b"".join(b"\x00" + raw[i].tobytes() for i in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))
