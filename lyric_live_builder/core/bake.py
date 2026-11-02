"""Plan -> BakedScene: nodes with rest poses and time tracks (design §5.7)."""
import math

import numpy as np

from . import model, registry, xform
from .lyrics import chunk_text
from .model import BakedScene, MeshSource, Node, Track

RATE = 30.0                                      # samples per second
TOL = {"location": 0.001, "rotation": 0.2 * math.pi / 180 / 2, "scale": 0.005, "color": 1 / 255}
ACCENT = (1.0, 0.82, 0.3)
WHITE = (1.0, 1.0, 1.0)


def rdp(times, values, tol):
    """Indices of the keys to keep so linear interpolation stays within tol of every sample
    (Ramer–Douglas–Peucker, max abs error over all components)."""
    n = len(times)
    if n <= 2:
        return np.arange(n)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        t = (times[a + 1:b] - times[a]) / (times[b] - times[a])
        line = values[a] + (values[b] - values[a]) * t[:, None]
        err = np.abs(values[a + 1:b] - line).max(axis=1)
        i = int(err.argmax())
        if err[i] > tol:
            m = a + 1 + i
            keep[m] = True
            stack.append((a, m))
            stack.append((m, b))
    return np.flatnonzero(keep)


def _track(node, prop, times, values, rest):
    """A decimated linear track, or None when it never leaves the rest value."""
    values = np.asarray(values, dtype=np.float64)
    if np.abs(values - np.asarray(rest)).max() <= TOL[prop]:
        return None
    idx = rdp(times, values, TOL[prop])
    return Track(node, prop, "linear", times[idx].astype(np.float32), values[idx].astype(np.float32))


def _push_out(world, eye):
    """Keep world points at least MIN_EYE_DISTANCE from the eye (design §7.2)."""
    v = world - eye
    d = np.linalg.norm(v, axis=-1, keepdims=True)
    far = np.maximum(d, model.MIN_EYE_DISTANCE)
    return eye + v / np.maximum(d, 1e-9) * far


def mesh_key(line, ch):
    if line.is_3d:
        return f"glyph3d|{line.font_role}|{ch}|{line.depth:.3f}|{line.bevel:.3f}"
    return f"glyph2d|{line.font_role}|{ch}"


def bake(plan, metrics, eye=model.EYE_HEIGHT, rate=RATE):
    """metrics(role) -> object with advance_em(ch) / vadvance_em(ch)."""
    nodes, meshes, tracks = [], {}, []
    eye_pt = np.array([0.0, 0.0, eye])
    for ln in plan.lines:
        lp = registry.get("layout", ln.layout)
        m = metrics(ln.font_role)
        dist = model.DISTANCE[ln.distance]
        angle = model.ANGLE_EMPH if ln.emphasis else model.ANGLE_BODY
        em = 2 * dist * math.tan(math.radians(angle) / 2)
        ctx = registry.LayoutCtx(
            text=ln.text, adv=[m.advance_em(c) for c in ln.text], vadv=[m.vadvance_em(c) for c in ln.text],
            em=em, distance=dist, eye=eye, is_3d=ln.is_3d, depth=ln.depth,
            chunks=chunk_text(ln.text), char_times=ln.char_times, anchor=ln.anchor, span=(ln.start, ln.end))
        params = dict(ln.layout_params)
        pl = lp.place(ctx, params)
        gid = f"line{ln.index:03d}"
        nodes.append(Node(gid, f"L{ln.index + 1:03d}_{ln.text[:12]}", "", "text", "group",
                          loc=tuple(pl.loc), rot=tuple(pl.rot)))
        if not pl.glyphs:
            continue
        g = len(pl.glyphs)
        rest_loc = np.array([gp.loc for gp in pl.glyphs], dtype=np.float64)
        rest_rot = np.array([xform.IDENTITY if gp.rot is None else gp.rot for gp in pl.glyphs], dtype=np.float64)
        ci = [gp.char_index for gp in pl.glyphs]

        # motion windows
        mctx = registry.MotionCtx(n=g, rest=rest_loc, em=pl.em, start=ln.start, end=ln.end,
                                  char_times=np.array([ln.char_times[i] for i in ci]), bpm=plan.bpm, seed=ln.seed)
        enter, hold, exit_ = (registry.get(k, n) for k, n in (("enter", ln.enter), ("hold", ln.hold), ("exit", ln.exit)))
        in_start = np.asarray(enter.windows(mctx, ln.enter_dur), dtype=np.float64)
        in_start = np.clip(in_start, ln.start, ln.end - ln.exit_dur - ln.enter_dur)
        in_end = in_start + ln.enter_dur
        out_start = ln.end - ln.exit_dur - exit_.stagger * (g - 1 - np.arange(g))
        out_start = np.maximum(out_start, in_end)
        out_dur = np.maximum(ln.end - out_start, 1e-3)

        t0, t1 = float(in_start.min()), ln.end
        times = np.unique(np.concatenate([np.arange(t0, t1, 1.0 / rate), [t1], in_end, out_start]))
        T = times[None, :]
        p_in = np.clip((T - in_start[:, None]) / max(ln.enter_dur, 1e-3), 0, 1)
        held = np.maximum(T - in_end[:, None], 0)
        p_out = np.clip((T - out_start[:, None]) / out_dur[:, None], 0, 1)
        d = enter.evaluate(mctx, p_in).then(hold.evaluate(mctx, held)).then(exit_.evaluate(mctx, p_out))

        loc = rest_loc[:, None, :] + xform.rotate(rest_rot[:, None, :], d.loc) * 1.0
        rot = xform.continuous(xform.mul(d.rot, rest_rot[:, None, :]))
        scale = d.scale * pl.em

        # group motion (approach, cube) and the eye-distance rule work in world space
        gm = lp.group_motion(ctx, params, pl, times)
        if gm is not None:
            g_loc, g_rot = gm
            g_rot = xform.continuous(np.asarray(g_rot))
            world = g_loc[None] + xform.rotate(g_rot[None], loc)
            t_g = _track(gid, "location", times, g_loc, pl.loc)
            r_g = _track(gid, "rotation", times, g_rot, pl.rot)
            tracks += [t for t in (t_g, r_g) if t is not None]
        else:
            g_rot = np.broadcast_to(pl.rot, (len(times), 4))
            world = pl.loc + xform.rotate(np.asarray(pl.rot)[None, None], loc)
        pushed = _push_out(world, eye_pt)
        if not np.allclose(pushed, world):
            inv = np.asarray(g_rot) * np.array([1, -1, -1, -1])
            g_loc_arr = gm[0] if gm is not None else np.asarray(pl.loc)[None]
            loc = xform.rotate(inv[None], pushed - g_loc_arr[None])

        base = [ACCENT if ln.emph_mask[i] else WHITE for i in ci]
        narrow = lp.shown(ctx, params, pl)
        for k in range(g):
            i = ci[k]
            ch = ln.text[i]
            key = mesh_key(ln, ch)
            if key not in meshes:
                meshes[key] = MeshSource(key, "glyph3d" if ln.is_3d else "glyph2d",
                                         {"role": ln.font_role, "char": ch, "depth": ln.depth, "bevel": ln.bevel})
            nid = f"{gid}_g{i:02d}"
            color = base[k] + (1.0,)
            nodes.append(Node(nid, f"{ch}", gid, "text", "glyph", mesh=key, material="text",
                              loc=tuple(rest_loc[k]), rot=tuple(rest_rot[k]), scale=(pl.em,) * 3,
                              color=color, default_active=False))
            on, off = float(in_start[k]), ln.end
            if narrow:
                on, off = max(on, narrow[k][0]), min(off, narrow[k][1])
            if off <= on:
                continue                         # never on stage
            keys = [(0.0, 0.0), (on, 1.0), (off, 0.0)] if on > 0 else [(on, 1.0), (off, 0.0)]
            tracks.append(Track(nid, "active", "constant", np.array([k_[0] for k_ in keys], dtype=np.float32),
                                np.array([[k_[1]] for k_ in keys], dtype=np.float32)))
            for prop, vals, rest in (("location", loc[k], rest_loc[k]), ("rotation", rot[k], rest_rot[k]),
                                     ("scale", scale[k], (pl.em,) * 3)):
                tr = _track(nid, prop, times, vals, rest)
                if tr:
                    tracks.append(tr)
            col = np.concatenate([np.broadcast_to(base[k], (len(times), 3)), d.alpha[k][:, None]], axis=1)
            tr = _track(nid, "color", times, col, color)
            if tr:
                tracks.append(tr)
    return BakedScene(duration=plan.duration, nodes=nodes, meshes=meshes, tracks=tracks, sections=plan.sections)


def world_positions(baked, t):
    """{glyph node id: world position} of glyphs active at time t (for checks and tests)."""
    by_id = {n.id: n for n in baked.nodes}
    tr = {}
    for x in baked.tracks:
        tr[(x.node, x.prop)] = x

    def value(nid, prop, rest):
        x = tr.get((nid, prop))
        if x is None:
            return np.asarray(rest, dtype=np.float64)
        if x.interp == "constant":
            k = np.searchsorted(x.times, t, side="right") - 1
            return x.values[max(k, 0)]
        return np.array([np.interp(t, x.times, x.values[:, c]) for c in range(x.values.shape[1])])

    out = {}
    for n in baked.nodes:
        if n.kind != "glyph" or value(n.id, "active", [1.0])[0] < 0.5:
            continue
        p = by_id[n.parent]
        g_loc = value(p.id, "location", p.loc)
        g_rot = xform.normalize(value(p.id, "rotation", p.rot))
        out[n.id] = g_loc + xform.rotate(g_rot, value(n.id, "location", n.loc))
    return out
