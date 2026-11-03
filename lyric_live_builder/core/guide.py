"""Gaze guidance before lines that appear away from where the audience is looking (spec §7.6, design §8.4).

The audience's gaze is estimated from the previous line; a line 30° or more away from it gets a
streak of light motes flowing from the gaze to the line (moving light draws the eye far better
than a static one), a soft glow where the line will appear, and, behind the audience, a lift of
the dome's brightness in that direction."""
import math

import numpy as np

from . import model, xform
from .model import MeshSource, Node, Track
from .parts.common import in_out_sine

ANGLE = math.radians(30)             # guide lines at least this far from the estimated gaze
LEAD = 0.7                           # the streak takes this long and arrives as the line appears
MOTE_LAG = 0.03                      # each mote trails the one before: close together they read as one streak
MIN_GAP = 0.5                        # at most two guides per second
EYE = np.array([0.0, 0.0, model.EYE_HEIGHT])
RATE = 30.0


def _first_on(tracks, nid):
    tr = tracks.get((nid, "active"))
    if tr is None:
        return None
    on = tr.times[np.flatnonzero(tr.values[:, 0] > 0.5)]
    return float(on[0]) if len(on) else None


def _centroid(positions, prefix):
    pts = [p for k, p in positions.items() if k.startswith(prefix)]
    return np.mean(pts, axis=0) if pts else None


def _unit(v):
    return v / max(np.linalg.norm(v), 1e-9)


def _angle(a, b):
    return math.acos(float(np.clip(np.dot(_unit(a), _unit(b)), -1, 1)))


def _slerp(u0, u1, s):
    ang = math.acos(float(np.clip(np.dot(u0, u1), -1, 1)))
    if ang < 1e-4:
        return np.broadcast_to(u0, s.shape + (3,)).copy()
    if math.pi - ang < 1e-3:                              # straight behind: go over the top
        mid = _unit(np.array([0.0, 0.0, 1.0]) - np.dot(u0, [0, 0, 1]) * u0)
        a = np.where(s < 0.5, 0.0, 1.0)
        first = _slerp(u0, mid, np.clip(s * 2, 0, 1))
        second = _slerp(mid, u1, np.clip(s * 2 - 1, 0, 1))
        return first * (1 - a)[..., None] + second * a[..., None]
    w0 = np.sin((1 - s) * ang) / math.sin(ang)
    w1 = np.sin(s * ang) / math.sin(ang)
    return w0[..., None] * u0 + w1[..., None] * u1


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _light(lp):
    """The line's colour as light: the brighter of text and accent, lifted toward white when dark
    (dark text on a bright sky would make an invisible additive glow)."""
    cols = lp.colors or {"fg": (1.0, 1.0, 1.0), "accent": (1.0, 0.82, 0.3)}
    c = np.array(max((cols["accent"], cols["fg"]) if lp.emphasis else (cols["fg"], cols["accent"]), key=_lum))
    if _lum(c) < 0.3:
        c = c + (1 - c) * 0.75
    return tuple(float(x) for x in c)


def plan_guides(plan, positions, tracks):
    """positions(t) -> {glyph node id: world position}; tracks: {(node, prop): Track} of the text."""
    strength = plan.fx.get("guide", model.FX_DEFAULTS["guide"])
    if strength <= 0:
        return []
    out = []
    for lp in plan.lines:
        prefix = f"line{lp.index:03d}_"
        ons = [t for t in (_first_on(tracks, nid) for (nid, prop) in tracks if prop == "active" and nid.startswith(prefix))
               if t is not None]
        if not ons or lp.guide == "off":
            continue
        t_hit = min(ons)
        target = _centroid(positions(t_hit + 0.35), prefix)
        if target is None:
            continue
        gaze = None
        for other in plan.lines:
            if other.index != lp.index and other.start < t_hit - 0.8 < other.end:
                c = _centroid(positions(t_hit - 0.8), f"line{other.index:03d}_")
                if c is not None:
                    gaze = c
        if gaze is None:
            gaze = EYE + np.array([0.0, np.linalg.norm(target - EYE), 0.0])
        ang = _angle(gaze - EYE, target - EYE)
        if ang < ANGLE and lp.guide != "on":
            continue
        if out and t_hit - out[-1]["t_hit"] < MIN_GAP:
            if ang <= out[-1]["angle"]:
                continue
            out.pop()
        kinds = ["streak", "glow"] + (["dome"] if ang > math.radians(90) else [])
        col = _light(lp)
        out.append({"line": lp.index, "t_on": t_hit - LEAD, "t_hit": t_hit, "from": [float(x) for x in gaze],
                    "to": [float(x) for x in _unit(target - EYE)], "target": [float(x) for x in target],
                    "angle": ang, "kinds": kinds, "color": tuple(col), "motes": 3 + int(round(3 * strength))})
    return out


def bake_guides(guides, track_fn):
    """Per guide, a pivot at the eye holding the motes and the glow (positions relative to the eye).
    The Udon version (design §10.7) turns the pivot about the line's direction so the streak starts
    from where that viewer really looks; the line's end of the streak stays put.
    track_fn(node, prop, times, values, rest) -> Track or None (decimated)."""
    nodes, tracks = [], []
    meshes = {"orb": MeshSource("orb", "orb", {})}
    for n, g in enumerate(guides):
        target, gaze = np.array(g["target"]), np.array(g["from"])
        u0, u1 = _unit(gaze - EYE), _unit(target - EYE)
        d0, d1 = np.linalg.norm(gaze - EYE), np.linalg.norm(target - EYE)
        rgb = tuple(g["color"])
        pid = f"guide{n:03d}"
        g["node"] = pid
        nodes.append(Node(pid, f"Guide_{g['line'] + 1:03d}", "", "guide", "group", loc=tuple(EYE)))
        for k in range(g["motes"]):
            nid = f"guide{n:03d}_m{k}"
            t0 = g["t_on"] + k * MOTE_LAG
            t1 = g["t_hit"] + k * MOTE_LAG
            times = np.unique(np.round(np.concatenate([np.arange(t0, t1 + 0.25, 1 / RATE), [t1, t1 + 0.25]]), 4))
            s = in_out_sine((times - t0) / (t1 - t0))
            dirs = _slerp(u0, u1, s)
            dirs[..., 2] += np.sin(math.pi * s) * math.radians(8)          # bow upward
            dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)
            dist = d0 + (d1 - d0) * s
            loc = EYE + dirs * dist[..., None]
            size = 0.026 * dist * (1 - 0.13 * k) * np.clip(1 - (times - t1) / 0.25, 0.2, 1)
            alpha = np.clip(np.minimum((times - t0) / (0.15 * LEAD), (t1 + 0.25 - times) / 0.25), 0, 1) * (1 - 0.14 * k)
            loc = loc - EYE
            nodes.append(Node(nid, f"Mote_{k}", pid, "guide", "mote", mesh="orb", material="glow",
                              loc=tuple(loc[0]), scale=(float(size[0]),) * 3, color=rgb + (0.0,), default_active=False))
            tracks.append(Track(nid, "active", "constant", np.array([0.0, t0, t1 + 0.25], dtype=np.float32),
                                np.array([[0.0], [1.0], [0.0]], dtype=np.float32)))
            for prop, vals, rest in (("location", loc, loc[0]), ("scale", np.repeat(size[:, None], 3, 1), (size[0],) * 3),
                                     ("color", np.column_stack([np.broadcast_to(rgb, (len(times), 3)), alpha]), rgb + (0.0,))):
                tr = track_fn(nid, prop, times, vals, rest)
                if tr:
                    tracks.append(tr)
        if "glow" in g["kinds"]:
            nid = f"guide{n:03d}_glow"
            loc = tuple(target + u1 * 0.3 - EYE)                            # just behind the text
            size = 0.12 * d1
            nodes.append(Node(nid, "Glow", pid, "guide", "glow", mesh="orb", material="glow",
                              loc=loc, scale=(size,) * 3, color=rgb + (0.0,), default_active=False))
            t_a, t_b = g["t_hit"] - 0.4, g["t_hit"] + 0.3
            tracks.append(Track(nid, "active", "constant", np.array([0.0, t_a, t_b], dtype=np.float32),
                                np.array([[0.0], [1.0], [0.0]], dtype=np.float32)))
            tracks.append(Track(nid, "color", "linear", np.array([t_a, g["t_hit"], t_b], dtype=np.float32),
                                np.array([rgb + (0.0,), rgb + (0.55,), rgb + (0.0,)], dtype=np.float32)))
    return nodes, tracks, meshes
