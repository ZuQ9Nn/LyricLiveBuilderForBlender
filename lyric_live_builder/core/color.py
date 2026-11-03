# Colour helpers ported from JIZURA (src/01_util.js: mix, lum, hsl, toHsl, contrast,
# fitContrast, randomPalette), MIT License, Copyright (c) 2026 hakoniwa.
"""Colours: '#RRGGBB' sRGB strings in the data, linear RGB tuples for Blender and the bake."""
import math


def rgb(hex_):
    """'#RGB' / '#RRGGBB' -> (r, g, b) 0..255."""
    h = str(hex_ or "#000").lstrip("#")
    if len(h) == 3:
        h = "".join(c + c for c in h)
    n = int(h[:6], 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def to_hex(r, g, b):
    return "#" + "".join(f"{round(min(255, max(0, v))):02X}" for v in (r, g, b))


def mix(h1, h2, t):
    a, b = rgb(h1), rgb(h2)
    return to_hex(*(x + (y - x) * t for x, y in zip(a, b)))


def lum(hex_):
    r, g, b = rgb(hex_)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def hsl(h, s, l):
    """h 0..360, s / l 0..1 -> hex."""
    h = (h % 360 + 360) % 360 / 360
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def f(t):
        t = (t + 1) % 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p
    return to_hex(f(h + 1 / 3) * 255, f(h) * 255, f(h - 1 / 3) * 255)


def to_hsl(hex_):
    r, g, b = (v / 255 for v in rgb(hex_))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s, l


def _rel_lum(hex_):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio."""
    x, y = _rel_lum(a), _rel_lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def fit_contrast(hex_, bg, minimum=3.0):
    """Nudge the lightness away from the background until the colour reads on it."""
    if contrast(hex_, bg) >= minimum:
        return hex_.upper()
    h, s, l = to_hsl(hex_)
    dark = lum(bg) < 0.5
    for _ in range(24):
        l = min(0.96, l + 0.035) if dark else max(0.04, l - 0.035)
        c = hsl(h, s, l)
        if contrast(c, bg) >= minimum:
            return c
    return "#FFFFFF" if dark else "#111111"


GHOST_PAIRS = [("#16F4D4", "#F5A50C"), ("#FF2A2A", "#2AA8FF"), ("#FF2BD6", "#2BFF88"), ("#FFE600", "#7B2BFF"),
               ("#FF6A00", "#00C2B8"), ("#FF6FAE", "#B6FF3B"), ("#00E0FF", "#FF3D6E"), ("#C8FF00", "#FF00A8"),
               ("#4D6BFF", "#FFB000"), ("#FF4B2B", "#2BD9FF")]


def random_palette(bg, rnd):
    """A fresh accent and a pair of side colours that work on the background (rnd() -> 0..1)."""
    dark = lum(bg) < 0.5
    if rnd() < 0.4:
        a, b = GHOST_PAIRS[math.floor(rnd() * len(GHOST_PAIRS)) % len(GHOST_PAIRS)]
        if rnd() < 0.5:
            a, b = b, a
        if not dark:
            a, b = hsl(to_hsl(a)[0], 0.95, 0.47), hsl(to_hsl(b)[0], 0.95, 0.47)
    else:
        h = rnd() * 360
        gap = (180, 165, 150, 135)[math.floor(rnd() * 4) % 4] * (1 if rnd() < 0.5 else -1)
        s = 0.82 + rnd() * 0.18
        l = 0.52 + rnd() * 0.1 if dark else 0.44 + rnd() * 0.08
        a, b = hsl(h, s, l), hsl(h + gap, s, l)
    r = rnd()
    ha, hb = to_hsl(a)[0], to_hsl(b)[0]
    acc = a if r < 0.35 else b if r < 0.6 else hsl((ha + hb) / 2 + (0 if rnd() < 0.5 else 180), 0.9, 0.6 if dark else 0.45)
    return {"accent": fit_contrast(acc, bg, 3.0), "ghostA": a, "ghostB": b}


def linear(hex_):
    """'#RRGGBB' (sRGB) -> linear (r, g, b) floats, the values Blender colour properties hold."""
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return tuple(lin(v) for v in rgb(hex_))
