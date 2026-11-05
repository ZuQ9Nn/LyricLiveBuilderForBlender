"""Plan.gimmicks / Plan.spectrum -> nodes and tracks (design §8.3).

A gimmick is a group node at its place on stage (it carries the way of appearing) with the visible
parts below it. Every part has its own `active` track: Blender does not hide children with their
parent."""
import math

import numpy as np

from . import color, model, xform
from .model import MeshSource, Node, Track
from .parts import gimmicks as parts

RATE = 30.0
GREY = (0.45, 0.47, 0.52)
BOX = (0.55, 0.42, 0.3)
LETTER = (1.0, 0.95, 0.8)
SWAY = 10 * math.pi / 180


def _out(s):
    return 1 - (1 - s) ** 3


def _back(s, over=1.7):
    return 1 + (over + 1) * (s - 1) ** 3 + over * (s - 1) ** 2


def _bounce(s):
    """0 at the top, 1 on the floor, two small hops after the first landing."""
    u = np.minimum(s / 0.6, 1.0)
    hop = np.clip((s - 0.6) / 0.4, 0, 1)
    return u * u - 0.14 * np.sin(math.pi * np.minimum(hop * 2, 1)) * (hop < 0.5) \
        - 0.04 * np.sin(math.pi * np.maximum(hop * 2 - 1, 0)) * (hop >= 0.5)


def _hex(c, fallback):
    return tuple(color.linear(c)) if c else fallback


def _active(nid, t0, t1):
    keys = [(0.0, 0.0), (t0, 1.0), (t1, 0.0)] if t0 > 0 else [(t0, 1.0), (t1, 0.0)]
    return Track(nid, "active", "constant", np.array([k[0] for k in keys], dtype=np.float32),
                 np.array([[k[1]] for k in keys], dtype=np.float32))


class _Gimmick:
    def __init__(self, n, g, track_fn):
        self.g, self.track_fn = g, track_fn
        self.id = f"gim{n:03d}"
        self.nodes, self.tracks, self.meshes = [], [], {}
        t0, t1 = g["start"], g["end"]
        self.times = np.unique(np.round(np.concatenate([np.arange(t0, t1, 1 / RATE), [t1]]), 4))
        self.dur = parts.SHOWS[g["show"]]["dur"]
        self.p = np.clip((self.times - t0) / self.dur, 0, 1)
        self.melt = g["show"] == "dissolve"
        exit_dur = self.dur if self.melt else parts.EXIT
        self.out = np.clip((self.times - (t1 - exit_dur)) / exit_dur, 0, 1)
        self.alpha = 1 - self.out
        if self.melt:
            self.alpha = self.alpha * self.p

    def part(self, suffix, name, kind, mesh, material, rgb, loc=(0, 0, 0), rot=(1, 0, 0, 0), scale=(1, 1, 1), src=None):
        nid = f"{self.id}_{suffix}"
        rgba = tuple(rgb) + (1.0,)
        self.nodes.append(Node(nid, name, self.id, "gimmicks", kind, mesh=mesh, material=material, loc=tuple(loc), rot=tuple(rot),
                               scale=tuple(scale), color=rgba, default_active=False))
        self.meshes[mesh] = src or MeshSource(mesh, "builtin", {})
        self.tracks.append(_active(nid, self.g["start"], self.g["end"]))
        vals = np.column_stack([np.broadcast_to(rgb, (len(self.times), 3)), self.alpha])
        self.add_track(nid, "color", vals, rgba)
        return nid

    def add_track(self, nid, prop, values, rest):
        tr = self.track_fn(nid, prop, self.times, values, rest)
        if tr:
            self.tracks.append(tr)

    def group(self):
        """The way of appearing, in the group node's location, rotation and scale."""
        g = self.g
        show, p, n = g["show"], self.p, len(self.times)
        size = g["size"]
        place = np.array([math.sin(g["az"]) * parts.RADIUS, math.cos(g["az"]) * parts.RADIUS, parts.AIR if g["air"] else 0.0])
        loc = np.tile(place, (n, 1))
        scale = np.ones((n, 3))
        tilt = np.zeros(n)
        if show == "floor":
            e = _back(p, 0.8)
            loc[:, 2] -= 0.35 * size * (1 - np.clip(e, 0, 1))
            scale[:, 2] = np.maximum(e, 0.02)
        elif show == "sky":
            loc[:, 2] += 5.0 * (1 - _bounce(p))
        elif show == "wall":
            e = _out(p)
            loc += (1 - e)[:, None] * np.array([math.sin(g["az"]), math.cos(g["az"]), 0.0]) * 2.5
            scale *= np.maximum(e, 0.02)[:, None]
        elif show == "pop":
            scale *= np.maximum(_back(p, 2.2), 0.02)[:, None]
        elif show == "flip":
            tilt = math.pi * (1 - (0.5 - 0.5 * np.cos(math.pi * p)))
        elif show == "open":
            scale *= np.maximum(_back(np.clip(p / 0.25, 0, 1), 1.2), 0.02)[:, None]
        if not self.melt:
            scale *= np.maximum(1 - self.out ** 2, 0.02)[:, None]
        settled = np.clip((self.times - (g["start"] + self.dur)) / 0.6, 0, 1)
        wave = np.sin(2 * math.pi * (self.times - g["start"]) / 4.0)
        q = xform.mul(xform.yaw(-g["az"] + SWAY * settled * wave), xform.pitch(tilt))
        if g["air"]:
            loc[:, 2] += 0.07 * settled * np.sin(2 * math.pi * (self.times - g["start"]) / 3.0)
        rest_q = tuple(xform.yaw(np.array(-g["az"])))
        self.nodes.insert(0, Node(self.id, f"G{g['line'] + 1:03d}_{g['tag'] or 'emblem'}", "", "gimmicks", "group",
                                  loc=tuple(place), rot=rest_q))
        self.add_track(self.id, "location", loc, place)
        self.add_track(self.id, "rotation", xform.continuous(q), rest_q)
        self.add_track(self.id, "scale", scale, (1, 1, 1))

    def body(self):
        g = self.g
        size = g["size"]
        if g["source"] == "builtin":
            self.part("obj", g["tag"], "gimmick", f"gimmick:{g['tag']}", "gimmick", _hex(g["color"], LETTER), scale=(size,) * 3)
        elif g["source"] == "user":
            key = f"user:{g['asset']['name']}"
            self.part("obj", g["tag"], "gimmick", key, "gimmick", (1.0, 1.0, 1.0), scale=(size,) * 3,
                      src=MeshSource(key, "user", dict(g["asset"])))

    def emblem(self, metrics):
        """The word in 3D letters above a floor disc (spec §8.3.1)."""
        g = self.g
        m = metrics(g["role"])
        chars = [c for c in g["word"] if not c.isspace()]
        adv = [m.advance_em(c) for c in chars]
        em = min(0.75, 2.6 / max(sum(adv), 0.1))
        x = -sum(adv) * em / 2
        rgb = tuple(g["accent"]) if g["accent"] else LETTER
        for k, (c, a) in enumerate(zip(chars, adv)):
            key = f"glyph3d|{g['role']}|{c}|0.200|0.015"
            self.part(f"g{k:02d}", c, "glyph", key, "text", rgb, loc=(x + a * em / 2, 0.0, 0.3 + em / 2), scale=(em,) * 3,
                      src=MeshSource(key, "glyph3d", {"role": g["role"], "char": c, "depth": 0.2, "bevel": 0.015}))
            x += a * em
        radius = max(sum(adv) * em / 2 + 0.25, 0.6)
        self.part("base", "Pedestal", "gimmick", "gimmick:plate", "gimmick", GREY, scale=(radius, radius, 1.0))

    def flip_plate(self):
        r = self.g["size"] * 0.75
        self.part("plate", "Plate", "gimmick", "gimmick:plate", "gimmick", GREY, scale=(r, r, 1.0))

    def box(self):
        """Four walls hinged at the floor and a lid; the object waits inside."""
        g, t = self.g, self.times
        size = g["size"]
        w, tall = size * 1.2, size * 1.15
        opening = np.clip(((t - g["start"]) / self.dur - 0.3) / 0.7, 0, 1)
        angle = (100 * math.pi / 180) * (0.5 - 0.5 * np.cos(math.pi * opening))
        for k in range(4):
            turn = xform.yaw(np.array(k * math.pi / 2))
            loc = xform.rotate(turn, np.array([0.0, -w / 2, 0.0]))
            nid = self.part(f"w{k}", f"Wall_{k}", "gimmick", "gimmick:panel", "gimmick", BOX, loc=loc, rot=turn, scale=(w, 1.0, tall))
            q = xform.mul(turn, xform.pitch(angle))
            self.add_track(nid, "rotation", xform.continuous(q), tuple(turn))
        rest = (w * 1.04, w * 1.04, 0.04)
        nid = self.part("lid", "Lid", "gimmick", "gimmick:bar", "gimmick", BOX, loc=(0, 0, tall), scale=rest)
        lift = np.minimum(opening * 2.5, 1.0)
        loc = np.column_stack([np.zeros((len(t), 2)), tall + 1.2 * lift])
        self.add_track(nid, "location", loc, (0, 0, tall))
        self.add_track(nid, "scale", np.outer(np.maximum(1 - lift ** 2, 0.02), rest), rest)


def gimmicks(plan, metrics, track_fn):
    nodes, tracks, meshes = [], [], {}
    for n, g in enumerate(plan.gimmicks):
        b = _Gimmick(n, g, track_fn)
        if g["source"] == "emblem":
            b.emblem(metrics)
        else:
            b.body()
        if g["show"] == "flip":
            b.flip_plate()
        elif g["show"] == "open":
            b.box()
        b.group()
        nodes += b.nodes
        tracks += b.tracks
        meshes.update(b.meshes)
    return nodes, tracks, meshes


def spectrum(plan, track_fn):
    """24 bars in a circle around the audience, bass in front (spec §8.3)."""
    sp = plan.spectrum
    if not sp or not sp["windows"]:
        return [], [], {}
    levels, rate = sp["levels"], sp["rate"]
    nodes, tracks = [], []
    step = max(1, int(round(rate / parts.BAR_RATE)))
    frames = np.arange(0, len(levels), step)
    times = frames / rate
    inside = np.zeros(len(times), dtype=bool)
    for a, b, _ in sp["windows"]:
        inside |= (times >= a) & (times <= b)
    if not inside.any():                                      # the choruses lie past the end of the song
        return [], [], {}
    times = np.round(times[inside], 4)
    held = levels[frames[inside]]
    for i in range(1, len(held)):                             # fall slowly, rise at once
        held[i] = np.maximum(held[i], held[i - 1] * 0.8)
    n = parts.BARS
    for k in range(n):
        band = min(min(k, n - k) * 2, levels.shape[1] - 1)
        az = k * 2 * math.pi / n
        nid = f"bar{k:02d}"
        rest = (parts.BAR_WIDTH, parts.BAR_WIDTH, parts.BAR_MIN)
        loc = (math.sin(az) * parts.BAR_RADIUS, math.cos(az) * parts.BAR_RADIUS, 0.0)
        rgb = tuple(sp["windows"][0][2])
        nodes.append(Node(nid, f"Bar_{k:02d}", "", "gimmicks", "gimmick", mesh="gimmick:bar", material="gimmick", loc=loc,
                          rot=tuple(xform.yaw(np.array(-az))), scale=rest, color=rgb + (1.0,), default_active=False))
        keys = sorted({0.0} | {x for w in sp["windows"] for x in w[:2]})
        on = [[float(any(a <= t < b for a, b, _ in sp["windows"]))] for t in keys]
        tracks.append(Track(nid, "active", "constant", np.array(keys, dtype=np.float32), np.array(on, dtype=np.float32)))
        ct = np.array([w[0] for w in sp["windows"]], dtype=np.float32)
        ct[0] = 0.0
        tracks.append(Track(nid, "color", "constant", ct,
                            np.array([tuple(w[2]) + (1.0,) for w in sp["windows"]], dtype=np.float32)))
        vals = np.column_stack([np.full((len(times), 2), parts.BAR_WIDTH), parts.BAR_MIN + parts.BAR_HEIGHT * held[:, band]])
        tr = track_fn(nid, "scale", times, vals, rest)
        if tr:
            tracks.append(tr)
    return nodes, tracks, {"gimmick:bar": MeshSource("gimmick:bar", "builtin", {})}
