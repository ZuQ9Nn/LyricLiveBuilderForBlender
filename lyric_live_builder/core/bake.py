"""Plan -> BakedScene: nodes with rest poses and time tracks (design §5.7)."""
import math

import numpy as np

from . import bake_gimmick, bake_world, guide, model, registry, xform
from .lyrics import chunk_text
from .model import BakedScene, MeshSource, Node, Track
from .parts.common import in_out_sine, out_cubic

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


def _track(node, prop, times, values, rest, interp="linear"):
    """A decimated track, or None when it never leaves the rest value. Constant tracks (frame
    stepping) keep a key wherever the value moved by more than the tolerance."""
    values = np.asarray(values, dtype=np.float64)
    if np.abs(values - np.asarray(rest)).max() <= TOL[prop]:
        return None
    if interp == "constant":
        idx, last = [0], values[0]
        for i in range(1, len(values)):
            if np.abs(values[i] - last).max() > TOL[prop]:
                idx.append(i)
                last = values[i]
        idx = np.array(idx)
    else:
        idx = rdp(times, values, TOL[prop])
    return Track(node, prop, interp, times[idx].astype(np.float32), values[idx].astype(np.float32))


def _scaled(d, k):
    """A motion delta made stronger / weaker by k (the motion strength); identity stays identity."""
    d.loc = d.loc * k
    w = np.clip(d.rot[..., 0], -1, 1)
    half = np.arccos(np.abs(w)) * k
    axis = d.rot[..., 1:] * np.sign(w + (w == 0))[..., None]
    n = np.linalg.norm(axis, axis=-1, keepdims=True)
    d.rot = np.concatenate([np.cos(half)[..., None], np.where(n > 1e-12, axis / np.maximum(n, 1e-12), 0) *
                            np.sin(half)[..., None]], axis=-1)
    d.scale = 1 + (d.scale - 1) * k
    return d


def _push_out(world, eye):
    """Keep world points at least MIN_EYE_DISTANCE from the eye (design §7.2)."""
    v = world - eye
    d = np.linalg.norm(v, axis=-1, keepdims=True)
    far = np.maximum(d, model.MIN_EYE_DISTANCE)
    return eye + v / np.maximum(d, 1e-9) * far


def _glide(anchor, window, times):
    """(T, 4) rotation about the eye that carries a line from straight ahead to its slot.
    Elevation settles early so a line bound for a far slot passes between the nearer slots."""
    az, el = anchor
    u = (times - window[0]) / (window[1] - window[0])
    now = xform.facing(az * in_out_sine(u), el * out_cubic(u / 0.5))
    return xform.mul(now, xform.facing(az, el) * np.array([1, -1, -1, -1]))


def mesh_key(line, ch):
    if line.is_3d:
        return f"glyph3d|{line.font_role}|{ch}|{line.depth:.3f}|{line.bevel:.3f}"
    return f"glyph2d|{line.font_role}|{ch}"


LINE_MIN_STILL = 1.0                             # seconds a line must stand still to be worth a line mesh


def _line_meshes(candidates, nodes, meshes, tracks):
    """Mobile: while a still line stands between its entrance and its exit, show one merged mesh
    instead of its letters (design §11.3); fewer draw calls when lines pile up."""
    by_id = {(t.node, t.prop): k for k, t in enumerate(tracks)}
    for gid, parts, t_on, t_off in candidates:
        key = f"line:{gid}"
        meshes[key] = MeshSource(key, "line", {"parts": [p[1:] for p in parts]})
        nodes.append(Node(f"{gid}_line", "Line", gid, "text", "line_mesh", mesh=key, material="text_line",
                          default_active=False))
        tracks.append(Track(f"{gid}_line", "active", "constant", np.array([0.0, t_on, t_off], dtype=np.float32),
                            np.array([[0.0], [1.0], [0.0]], dtype=np.float32)))
        for nid, *_ in parts:
            k = by_id[(nid, "active")]
            tr = tracks[k]
            on, off = float(tr.times[-2] if len(tr.times) == 3 else tr.times[0]), float(tr.times[-1])
            keys = [(0.0, 0.0), (on, 1.0), (t_on, 0.0), (t_off, 1.0), (off, 0.0)] if on > 0 else \
                [(on, 1.0), (t_on, 0.0), (t_off, 1.0), (off, 0.0)]
            tracks[k] = Track(nid, "active", "constant", np.array([x[0] for x in keys], dtype=np.float32),
                              np.array([[x[1]] for x in keys], dtype=np.float32))


def bake(plan, metrics, eye=model.EYE_HEIGHT, rate=RATE, mobile=False, tmp=False, udon=False):
    """metrics(role) -> object with advance_em(ch) / vadvance_em(ch). mobile: add line meshes (§11.3);
    tmp: flat lines become TextMesh Pro letters in Unity, so only 3D lines get line meshes;
    udon: gaze guides timed for Udon sync (§10.7)."""
    nodes, meshes, tracks = [], {}, []
    line_candidates = []
    eye_pt = np.array([0.0, 0.0, eye])
    fx = plan.fx or model.FX_DEFAULTS
    koma = int(fx.get("koma", 0) or 0)                   # 12 / 8 = frame stepping (constant keys)
    interp = "constant" if koma else "linear"
    rate = koma or rate
    motion = fx.get("motion", model.FX_DEFAULTS["motion"])
    k_motion = 0.55 + 0.65 * motion                       # 0.7 -> about 1 (the parts' own amplitude)
    for ln in (cut for line in plan.lines for cut in line.cuts or [line]):
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
        # "line003_" finds the letters of all cuts of a line (the gaze estimate relies on it)
        gid = f"line{ln.index:03d}_c{ln.cut}" if ln.cut else f"line{ln.index:03d}"
        name = f"L{ln.index + 1:03d}-{ln.cut + 1}" if ln.cut else f"L{ln.index + 1:03d}"
        nodes.append(Node(gid, f"{name}_{ln.text[:12]}", "", "text", "group",
                          loc=tuple(pl.loc), rot=tuple(pl.rot)))
        if not pl.glyphs:
            continue
        g = len(pl.glyphs)
        rest_loc = np.array([gp.loc for gp in pl.glyphs], dtype=np.float64)
        rest_rot = np.array([xform.IDENTITY if gp.rot is None else gp.rot for gp in pl.glyphs], dtype=np.float64)
        ci = [gp.char_index for gp in pl.glyphs]

        # motion windows
        mctx = registry.MotionCtx(n=g, rest=rest_loc, em=pl.em, start=ln.start, end=ln.end,
                                  char_times=np.array([ln.char_times[i] for i in ci]), bpm=plan.bpm, seed=ln.seed,
                                  strength=motion)
        enter, hold, exit_ = (registry.get(k, n) for k, n in (("enter", ln.enter), ("hold", ln.hold), ("exit", ln.exit)))
        in_start = np.asarray(enter.windows(mctx, ln.enter_dur), dtype=np.float64)
        in_start = np.clip(in_start, ln.start, ln.end - ln.exit_dur - ln.enter_dur)
        in_end = in_start + ln.enter_dur
        out_start = ln.end - ln.exit_dur - exit_.stagger * (g - 1 - np.arange(g))
        out_start = np.maximum(out_start, in_end)
        out_dur = np.maximum(ln.end - out_start, 1e-3)

        t0, t1 = float(in_start.min()), ln.end
        # keys at least 0.1 ms apart: closer ones meet as float32 frame numbers and Blender merges them
        extra = [[t1]] if koma else [[t1], in_end, out_start]
        times = np.unique(np.round(np.concatenate([np.arange(t0, t1, 1.0 / rate)] + extra), 4))
        T = times[None, :]
        p_in = np.clip((T - in_start[:, None]) / max(ln.enter_dur, 1e-3), 0, 1)
        held = np.maximum(T - in_end[:, None], 0)
        p_out = np.clip((T - out_start[:, None]) / out_dur[:, None], 0, 1)
        d = _scaled(enter.evaluate(mctx, p_in), k_motion).then(hold.evaluate(mctx, held)).then(
            _scaled(exit_.evaluate(mctx, p_out), k_motion))

        loc = rest_loc[:, None, :] + xform.rotate(rest_rot[:, None, :], d.loc) * 1.0
        rot = xform.continuous(xform.mul(d.rot, rest_rot[:, None, :]))
        scale = d.scale * pl.em

        # group motion (approach, cube), the glide of kept lines and the eye-distance rule work in world space
        gm = lp.group_motion(ctx, params, pl, times)
        if gm is None:
            g_loc = np.broadcast_to(np.asarray(pl.loc, dtype=np.float64), (len(times), 3))
            g_rot = np.broadcast_to(np.asarray(pl.rot, dtype=np.float64), (len(times), 4))
        else:
            g_loc, g_rot = np.asarray(gm[0], dtype=np.float64), xform.continuous(np.asarray(gm[1]))
        if ln.glide:
            q = _glide(ln.anchor, ln.glide, times)
            g_loc = eye_pt + xform.rotate(q, g_loc - eye_pt)
            g_rot = xform.continuous(xform.mul(q, g_rot))
        for prop, vals, rest in (("location", g_loc, pl.loc), ("rotation", g_rot, pl.rot)):
            tr = _track(gid, prop, times, vals, rest, interp)
            if tr:
                tracks.append(tr)
        world = g_loc[None] + xform.rotate(g_rot[None], loc)
        pushed = _push_out(world, eye_pt)
        if not np.allclose(pushed, world):
            inv = g_rot * np.array([1, -1, -1, -1])
            loc = xform.rotate(inv[None], pushed - g_loc[None])

        fg, accent = (ln.colors["fg"], ln.colors["accent"]) if ln.colors else (WHITE, ACCENT)
        base = [tuple(accent) if ln.emph_mask[i] else tuple(fg) for i in ci]
        narrow = lp.shown(ctx, params, pl)
        parts = []
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
            parts.append((nid, key, tuple(rest_loc[k]), tuple(rest_rot[k]), float(pl.em), tuple(base[k])))
            keys = [(0.0, 0.0), (on, 1.0), (off, 0.0)] if on > 0 else [(on, 1.0), (off, 0.0)]
            tracks.append(Track(nid, "active", "constant", np.array([k_[0] for k_ in keys], dtype=np.float32),
                                np.array([[k_[1]] for k_ in keys], dtype=np.float32)))
            for prop, vals, rest in (("location", loc[k], rest_loc[k]), ("rotation", rot[k], rest_rot[k]),
                                     ("scale", scale[k], (pl.em,) * 3)):
                tr = _track(nid, prop, times, vals, rest, interp)
                if tr:
                    tracks.append(tr)
            col = np.concatenate([np.broadcast_to(base[k], (len(times), 3)), d.alpha[k][:, None]], axis=1)
            tr = _track(nid, "color", times, col, color, interp)
            if tr:
                tracks.append(tr)
        t_on, t_off = float(in_end.max()), float(out_start.min())
        if (mobile and ln.hold == "still" and not narrow and len(parts) > 1 and t_off - t_on >= LINE_MIN_STILL
                and (ln.is_3d or not tmp)):
            line_candidates.append((gid, parts, t_on, t_off))
    # gaze guidance needs the text's world positions; the dome takes its cues
    text = BakedScene(duration=plan.duration, nodes=nodes, meshes=meshes, tracks=tracks, sections=plan.sections)
    by_key = {(t.node, t.prop): t for t in tracks}
    guides = guide.plan_guides(plan, lambda t: world_positions(text, t), by_key, udon)
    _line_meshes(line_candidates, nodes, meshes, tracks)       # after the guides: they read the letters
    g_nodes, g_tracks, g_meshes = guide.bake_guides(guides, _track)
    nodes, tracks = nodes + g_nodes, tracks + g_tracks
    meshes.update(g_meshes)
    emitters = []
    if plan.world:
        d_node, d_tracks = bake_world.dome(plan, guides)
        f_nodes, f_tracks, f_meshes = bake_world.far_objects(plan)
        e_nodes, e_tracks, emitters = bake_world.emitters(plan)
        nodes += [d_node] + f_nodes + e_nodes
        tracks += d_tracks + f_tracks + e_tracks
        meshes.update(f_meshes)
        meshes[bake_world.DOME] = MeshSource(bake_world.DOME, "dome", {})
    for part_nodes, part_tracks, part_meshes in (bake_gimmick.gimmicks(plan, metrics, _track), bake_gimmick.spectrum(plan, _track)):
        nodes += part_nodes
        tracks += part_tracks
        meshes.update(part_meshes)
    return BakedScene(duration=plan.duration, nodes=nodes, meshes=meshes, tracks=tracks, sections=plan.sections,
                      emitters=emitters, guides=guides)


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
