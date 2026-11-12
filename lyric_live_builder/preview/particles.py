"""Particle preview: each frame, core.parts.particles.state() is evaluated and written into the
emitter's mesh (billboard quads facing the eye, or 3D shapes). Fixed topology: dead particles
collapse to zero size, so only vertex positions and colours change (design §8.1, §17.5)."""
import json

import bpy
import numpy as np

from ..core import atlas, meshes, model, xform
from ..core.parts import lines, particles as pts
from . import materials

PROP = "llb_emitter"
EYE = np.array([0.0, 0.0, model.EYE_HEIGHT])
_cache = {}                          # object name -> (json string, spec, 3D shapes, axes)


def _spec(ob):
    raw = ob.get(PROP)
    hit = _cache.get(ob.name)
    if hit and hit[0] == raw:
        return hit
    spec = json.loads(raw)
    p = spec["preset"]
    cap = spec["count"] + spec["pool"]
    if lines.is_lines(p):                                 # line effects: the segments stand in for the 3D layout
        shape = lines.geometry(p, spec["seed"], spec["colors"])
    else:
        shape = _layout3d(p, spec["seed"], cap) if p["shape"] in pts.SHAPES_3D else None
    rng = np.random.default_rng(spec["seed"] % (2 ** 32))
    axes = rng.normal(size=(cap, 3))
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    hit = (raw, spec, shape, axes)
    _cache[ob.name] = hit
    return hit


def _layout3d(p, seed, cap):
    """3D particles grouped by shape: [(slots, verts, faces)] in vertex order (each slot keeps its shape)."""
    which = pts.particle_shapes(p, seed, cap)
    out = []
    for k, name in enumerate(pts.shapes_of(p)):
        slots = np.flatnonzero(which == k)
        if len(slots):
            v, f = meshes.particle_shape(name)
            out.append((slots, np.asarray(v, dtype=np.float64), f))
    return out


def create(name, spec, collection):
    """Mesh object with capacity-many quads / shapes; the handler moves them."""
    p = spec["preset"]
    cap = max(1, spec["count"] + spec["pool"])
    me = bpy.data.meshes.new(name)
    if lines.is_lines(p):
        _create_lines(me, lines.geometry(p, spec["seed"], spec["colors"]))
    elif p["shape"] in pts.SHAPES_3D:
        faces, base = [], 0
        for slots, v, f in _layout3d(p, spec["seed"], cap):
            nv = len(v)
            faces += [tuple(base + i + k * nv for i in face) for k in range(len(slots)) for face in f]
            base += nv * len(slots)
        me.from_pydata(np.zeros((base, 3)).tolist(), [], faces)
        me.materials.append(materials.particle3d_material())
    else:
        quads = cap * (1 + _tail_len(p))                  # heads, then the tail segments (design §8.1)
        verts = np.zeros((quads * 4, 3))
        faces = [(4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3) for k in range(quads)]
        me.from_pydata(verts.tolist(), [], faces)
        uv = me.uv_layers.new(name="UVMap")
        first, _ = pts.tile_range(p)
        tiles = first + pts.particle_shapes(p, spec["seed"], cap)              # one shape per particle slot
        quad = []
        for t in tiles:
            u0, v0, u1, v1 = atlas.tile_uv(int(t))
            if p.get("beam"):                             # a beam is one solid band: the middle of its dot
                quad.append([[(u0 + u1) / 2, (v0 + v1) / 2]] * 4)
                continue
            quad.append([[u0, v0], [u1, v0], [u1, v1], [u0, v1]])
        u0, v0, u1, v1 = atlas.tile_uv(pts.SHAPES_2D.index("circle_dot"))
        quad += [[[(u0 + u1) / 2, (v0 + v1) / 2]] * 4] * (quads - cap)         # tail: the solid middle of a dot
        uv.data.foreach_set("uv", np.asarray(quad, dtype=np.float32).ravel())
        me.materials.append(materials.particle_material(p.get("blend") == "add"))
    me.attributes.new(materials.COLOR_ATTR, "FLOAT_COLOR", "POINT")
    me[PROP] = True                                       # removed with the preview (not shared)
    ob = bpy.data.objects.new(name, me)
    ob[PROP] = json.dumps(spec)
    collection.objects.link(ob)
    return ob


def _create_lines(me, geo):
    """Quads of a line effect; UVs pick the look: dots = a round dot, soft = the soft dot's cross-section,
    else the solid middle of the dot."""
    q = len(geo["width"])
    me.from_pydata(np.zeros((q * 4, 3)).tolist(), [], [(4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3) for k in range(q)])
    u0, v0, u1, v1 = atlas.tile_uv(pts.SHAPES_2D.index("circle_dot"))
    s0, t0, s1, t1 = atlas.tile_uv(pts.SHAPES_2D.index("soft_dot"))
    mid, smid = [(u0 + u1) / 2, (v0 + v1) / 2], (t0 + t1) / 2
    dot = [[u0, v0], [u1, v0], [u1, v1], [u0, v1]]
    soft = [[s0, smid], [s1, smid], [s1, smid], [s0, smid]]                    # across the width
    uv = [dot if d > 0.5 else soft if f > 0.5 else [mid] * 4 for d, f in zip(geo["dot"], geo["soft"])]
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", np.asarray(uv, dtype=np.float32).ravel())
    me.materials.append(materials.particle_material(True))


def _tail_len(p):
    return pts.TAIL_POINTS if p.get("tail") else 0


def _tail(st, p):
    """Tail segments head -> older points, facing the eye, narrowing and fading (vertex order: slot-major)."""
    pts_ = np.concatenate([st["pos"][:, None], st["tail"]], axis=1)          # (cap, K + 1, 3)
    a, b = pts_[:, :-1], pts_[:, 1:]
    k = pts.TAIL_POINTS
    w = p["tail"]["width"] * (1 - np.arange(k + 1) / k)                       # tapers to 0
    view = (a + b) / 2 - EYE
    side = np.cross(view, b - a)
    side /= np.maximum(np.linalg.norm(side, axis=-1, keepdims=True), 1e-9)
    wa, wb = (w[:-1] / 2)[None, :, None], (w[1:] / 2)[None, :, None]
    corners = [a - side * wa, a + side * wa, b + side * wb, b - side * wb]
    return np.stack(corners, axis=2).reshape(-1, 3)


def _billboards(st, p):
    c = st["pos"]
    d = c - EYE
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    up = np.where(np.abs(d[:, 2:3]) > 0.98, [[0.0, 1.0, 0.0]], [[0.0, 0.0, 1.0]])
    right = np.cross(d, up)
    right /= np.maximum(np.linalg.norm(right, axis=1, keepdims=True), 1e-9)
    upv = np.cross(right, d)
    s = st["size"][:, None]
    trail = p.get("trail")
    beam = p.get("beam")
    if beam:                                              # from the particle forward along its velocity
        n = np.linalg.norm(st["vel"], axis=1, keepdims=True)
        a = np.where(n > 1e-6, st["vel"] / np.maximum(n, 1e-9), upv)
        b = np.cross(d, a)
        b /= np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-9)
        w = s / 2
        end = c + a * beam["length"]
        corners = [c - b * w, c + b * w, end + b * w, end - b * w]
    elif trail:
        v = st["vel"] - np.sum(st["vel"] * d, axis=1, keepdims=True) * d
        n = np.linalg.norm(v, axis=1, keepdims=True)
        a = np.where(n > 1e-6, v / np.maximum(n, 1e-9), upv)
        b = np.cross(d, a)
        length = n * trail + s
        corners = [c - a * length - b * s / 2, c - a * length + b * s / 2, c + a * s / 2 + b * s / 2, c + a * s / 2 - b * s / 2]
    else:
        cs, sn = np.cos(st["spin"])[:, None], np.sin(st["spin"])[:, None]
        r, u = cs * right + sn * upv, -sn * right + cs * upv
        corners = [c + (-r - u) * s / 2, c + (r - u) * s / 2, c + (r + u) * s / 2, c + (-r + u) * s / 2]
    return np.stack(corners, axis=1).reshape(-1, 3), 4


def _shapes(st, layout, axes):
    """Vertex positions of the 3D particles (grouped by shape) and each slot's vertex count, in vertex order."""
    half = st["spin"][:, None] * 0.5
    q = np.concatenate([np.cos(half), axes * np.sin(half)], axis=1)
    co, per = [], []
    for slots, v, _ in layout:
        local = v[None] * st["size"][slots][:, None, None]
        if "size3" in st:                                 # per-axis sizes (slabs)
            local = local * st["size3"][slots][:, None, :]
        co.append((xform.rotate(q[slots][:, None], local) + st["pos"][slots][:, None]).reshape(-1, 3))
        per.append((slots, len(v)))
    return np.concatenate(co), per


def update(ob, t):
    raw, spec, shape, axes = _spec(ob)
    if lines.is_lines(spec["preset"]):
        co, col = lines.state(spec, shape, t)
        me = ob.data
        if len(me.vertices) == len(co):
            me.vertices.foreach_set("co", co.astype(np.float32).ravel())
            me.attributes[materials.COLOR_ATTR].data.foreach_set("color", col.astype(np.float32).ravel())
            me.update()
        return
    st = pts.state(spec, t)
    dead = st["alpha"] <= 0
    st["size"] = np.where(dead, 0.0, st["size"])
    tail = _tail_len(spec["preset"])
    if shape is not None:
        co, per = _shapes(st, shape, axes)
    else:
        co, per = _billboards(st, spec["preset"])
        if tail:
            co = np.concatenate([co, _tail(st, spec["preset"])])
    me = ob.data
    if len(me.vertices) != len(co):
        return
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    rgba = np.concatenate([st["color"], st["alpha"][:, None]], axis=1)
    if isinstance(per, list):                                    # 3D: grouped by shape
        col = np.concatenate([np.repeat(rgba[slots], nv, axis=0) for slots, nv in per])
    else:
        col = np.repeat(rgba, per, axis=0)
        if tail:
            fade = 0.8 * (1 - np.arange(tail) / tail)                               # older = fainter
            seg = np.repeat(rgba[:, None], tail, axis=1)
            seg[..., 3] *= fade
            col = np.concatenate([col, np.repeat(seg.reshape(-1, 4), 4, axis=0)])
    me.attributes[materials.COLOR_ATTR].data.foreach_set("color", col.astype(np.float32).ravel())
    me.update()


def update_scene(scene):
    fps = scene.render.fps / scene.render.fps_base
    t = (scene.frame_current - scene.frame_start + scene.frame_subframe) / fps
    for ob in scene.objects:
        if PROP in ob and ob.type == "MESH":
            update(ob, t)


@bpy.app.handlers.persistent
def _on_frame(scene, depsgraph=None):
    try:
        update_scene(scene)
    except Exception as e:                                # never break playback
        print("[LLB] particle preview:", e)


def register():
    if _on_frame not in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.append(_on_frame)


def unregister():
    if _on_frame in bpy.app.handlers.frame_change_pre:
        bpy.app.handlers.frame_change_pre.remove(_on_frame)
    _cache.clear()
