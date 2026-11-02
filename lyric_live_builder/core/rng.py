# Ported from JIZURA (src/01_util.js), MIT License, Copyright (c) 2026 hakoniwa.
"""Deterministic hashing, random streams, easing and 1D noise.

JS 32-bit semantics (Math.imul, |0, >>>0) are reproduced with uint32 arithmetic, so the
values match the browser version bit for bit.
"""
import math

import numpy as np

M32 = 0xFFFFFFFF
TAU = math.pi * 2
DEG = math.pi / 180


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, t):
    return a + (b - a) * t


def inv(a, b, x):
    return 0.0 if b == a else (x - a) / (b - a)


def smooth(a, b, x):
    t = clamp(inv(a, b, x))
    return t * t * (3 - 2 * t)


def js_round(x):
    """Math.round: halves round up (Python's round() rounds halves to even)."""
    return math.floor(x + 0.5)


def _u32(x):
    """JS ToInt32 as uint32 bits: truncate toward zero, wrap modulo 2^32."""
    if isinstance(x, float):
        if not math.isfinite(x):
            return 0
        x = math.trunc(x)
    return int(x) & M32


def _mul(a, b):
    return (a * b) & M32


# ---- easing (J.E) ----

def _c(f):
    return lambda x, *a: f(clamp(x), *a)


def _in_out_expo(x):
    if x <= 0 or x >= 1:
        return x
    return 2 ** (20 * x - 10) / 2 if x < 0.5 else (2 - 2 ** (-20 * x + 10)) / 2


def _out_back(x, s=1.9):
    c = s + 1
    return 1 + c * (x - 1) ** 3 + s * (x - 1) ** 2


def _out_elastic(x):
    if x == 0 or x == 1:
        return x
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (TAU / 3)) + 1


E = {
    "lin": _c(lambda x: x),
    "inQuad": _c(lambda x: x * x),
    "outQuad": _c(lambda x: 1 - (1 - x) * (1 - x)),
    "inCubic": _c(lambda x: x * x * x),
    "outCubic": _c(lambda x: 1 - (1 - x) ** 3),
    "inOutCubic": _c(lambda x: 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2),
    "outExpo": _c(lambda x: 1.0 if x >= 1 else 1 - 2 ** (-10 * x)),
    "inExpo": _c(lambda x: 0.0 if x <= 0 else 2 ** (10 * x - 10)),
    "inOutExpo": _c(_in_out_expo),
    "outBack": _c(_out_back),
    "outElastic": _c(_out_elastic),
    "inOutSine": _c(lambda x: -(math.cos(math.pi * x) - 1) / 2),
}


# ---- hashing ----

def sid(s):
    """String -> uint32 (FNV-1a over UTF-16 code units, like charCodeAt)."""
    h = 2166136261
    b = s.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h ^= b[i] | (b[i + 1] << 8)
        h = _mul(h, 16777619)
    return h


def h(a=0, b=0, c=0, d=0, e=0):
    """Up to 5 numeric keys -> uint32 (J.h)."""
    x = 0x9E3779B9 ^ _u32(a)
    x = _mul(x ^ (x >> 16), 0x85EBCA6B)
    x = (x + _mul(_u32(b) + 0x632BE5AB, 0xC2B2AE35)) & M32
    x = _mul(x ^ (x >> 13), 0xC2B2AE35)
    x = (x + _mul(_u32(c) + 0x5BD1E995, 0x27D4EB2F)) & M32
    x = _mul(x ^ (x >> 15), 0x165667B1)
    x = (x + _mul(_u32(d) + 0x1B873593, 0x85EBCA6B)) & M32
    x = _mul(x ^ (x >> 16), 0x27D4EB2F)
    x = (x + _mul(_u32(e) + 0x68E31DA4, 0x9E3779B1)) & M32
    x ^= x >> 15
    x = _mul(x, 0x2C1B3C6D)
    x ^= x >> 12
    x = _mul(x, 0x297A2D39)
    x ^= x >> 15
    return x


def r(a=0, b=0, c=0, d=0, e=0):
    return h(a, b, c, d, e) / 4294967296


def rs(a=0, b=0, c=0, d=0, e=0):
    return r(a, b, c, d, e) * 2 - 1


def rr(lo, hi, a=0, b=0, c=0, d=0, e=0):
    return lo + (hi - lo) * r(a, b, c, d, e)


def pick(arr, a=0, b=0, c=0, d=0):
    return arr[math.floor(r(a, b, c, d) * len(arr)) % len(arr)]


class Rng:
    """mulberry32 stream (J.rng)."""

    def __init__(self, seed):
        self.s = _u32(seed)

    def __call__(self):
        self.s = (self.s + 0x6D2B79F5) & M32
        t = self.s
        t = _mul(t ^ (t >> 15), t | 1)
        t ^= (t + _mul(t ^ (t >> 7), t | 61)) & M32
        return (t ^ (t >> 14)) / 4294967296

    def range(self, lo, hi):
        return lo + (hi - lo) * self()

    def int(self, lo, hi):
        return math.floor(lo + (hi - lo + 1) * self())

    def pick(self, arr):
        return arr[math.floor(self() * len(arr)) % len(arr)]

    def chance(self, p):
        return self() < p

    def wpick(self, items):
        """items: [(value, weight)] or [{'v': value, 'w': weight}]."""
        pairs = [(it["v"], it["w"]) if isinstance(it, dict) else (it[0], it[1]) for it in items]
        x = self() * sum(w for _, w in pairs)
        for v, w in pairs:
            x -= w
            if x <= 0:
                return v
        return pairs[-1][0]


def noise1(x, seed=0):
    """Smooth 1D value noise in -1..1."""
    i = math.floor(x)
    f = x - i
    u = f * f * (3 - 2 * f)
    return lerp(rs(seed, i), rs(seed, i + 1), u)


# ---- vectorized versions for motion evaluation over time arrays ----

def _np_u32(x):
    x = np.asarray(x)
    if x.dtype.kind == "f":
        x = np.trunc(np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0))
        x = np.mod(x, 4294967296.0)
    return x.astype(np.int64).astype(np.uint64) & np.uint64(M32)          # numpy 1.x (Blender 5.0) needs the cast


def _np_mul(a, b):
    return (a * np.uint64(b) if isinstance(b, int) else a * b) & np.uint64(M32)


def h_np(a=0, b=0, c=0, d=0, e=0):
    """Vectorized h(); arguments broadcast, result is a uint32 array."""
    m = np.uint64(M32)
    a, b, c, d, e = (_np_u32(v) for v in (a, b, c, d, e))
    x = np.uint64(0x9E3779B9) ^ a
    x = _np_mul(x ^ (x >> np.uint64(16)), 0x85EBCA6B)
    x = (x + _np_mul((b + np.uint64(0x632BE5AB)) & m, 0xC2B2AE35)) & m
    x = _np_mul(x ^ (x >> np.uint64(13)), 0xC2B2AE35)
    x = (x + _np_mul((c + np.uint64(0x5BD1E995)) & m, 0x27D4EB2F)) & m
    x = _np_mul(x ^ (x >> np.uint64(15)), 0x165667B1)
    x = (x + _np_mul((d + np.uint64(0x1B873593)) & m, 0x85EBCA6B)) & m
    x = _np_mul(x ^ (x >> np.uint64(16)), 0x27D4EB2F)
    x = (x + _np_mul((e + np.uint64(0x68E31DA4)) & m, 0x9E3779B1)) & m
    x ^= x >> np.uint64(15)
    x = _np_mul(x, 0x2C1B3C6D)
    x ^= x >> np.uint64(12)
    x = _np_mul(x, 0x297A2D39)
    x ^= x >> np.uint64(15)
    return x.astype(np.uint32)


def noise1_np(x, seed=0):
    x = np.asarray(x, dtype=np.float64)
    i = np.floor(x)
    f = x - i
    u = f * f * (3 - 2 * f)
    a = h_np(seed, i) / 4294967296 * 2 - 1
    b = h_np(seed, i + 1) / 4294967296 * 2 - 1
    return a + (b - a) * u
