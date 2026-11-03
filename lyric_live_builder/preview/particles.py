"""Particle preview: each frame, core.parts.particles.state() is evaluated and written into the
emitter's mesh (billboard quads facing the eye, or 3D shapes). Fixed topology: dead particles
collapse to zero size, so only vertex positions and colours change (design §8.1, §17.5)."""
import json

import bpy
import numpy as np

from ..core import atlas, meshes, model, xform
from ..core.parts import particles as pts
from . import materials

PROP = "llb_emitter"
EYE = np.array([0.0, 0.0, model.EYE_HEIGHT])
_cache = {}                          # object name -> (json string, spec, local shape, axes)


def _spec(ob):
    raw = ob.get(PROP)
    hit = _cache.get(ob.name)
    if hit and hit[0] == raw:
        return hit
    spec = json.loads(raw)
    p = spec["preset"]
    cap = spec["count"] + spec["pool"]
    shape = meshes.particle_shape(p["shape"]) if p["shape"] in pts.SHAPES_3D else None
    rng = np.random.default_rng(spec["seed"] % (2 ** 32))
    axes = rng.normal(size=(cap, 3))
    axes /= np.linalg.norm(axes, axis=1, keepdims=True)
    hit = (raw, spec, shape, axes)
    _cache[ob.name] = hit
    return hit


def create(name, spec, collection):
    """Mesh object with capacity-many quads / shapes; the handler moves them."""
    p = spec["preset"]
    cap = max(1, spec["count"] + spec["pool"])
    me = bpy.data.meshes.new(name)
    if p["shape"] in pts.SHAPES_3D:
        v, f = meshes.particle_shape(p["shape"])
        nv = len(v)
        verts = np.zeros((cap * nv, 3))
        faces = [tuple(i + k * nv for i in face) for k in range(cap) for face in f]
        me.from_pydata(verts.tolist(), [], faces)
        me.materials.append(materials.particle3d_material())
    else:
        verts = np.zeros((cap * 4, 3))
        faces = [(4 * k, 4 * k + 1, 4 * k + 2, 4 * k + 3) for k in range(cap)]
        me.from_pydata(verts.tolist(), [], faces)
        uv = me.uv_layers.new(name="UVMap")
        u0, v0, u1, v1 = atlas.tile_uv(pts.SHAPES_2D.index(p["shape"]))
        uvs = np.tile(np.array([[u0, v0], [u1, v0], [u1, v1], [u0, v1]], dtype=np.float32), (cap, 1))
        uv.data.foreach_set("uv", uvs.ravel())
        me.materials.append(materials.particle_material(p.get("blend") == "add"))
    me.attributes.new(materials.COLOR_ATTR, "FLOAT_COLOR", "POINT")
    me[PROP] = True                                       # removed with the preview (not shared)
    ob = bpy.data.objects.new(name, me)
    ob[PROP] = json.dumps(spec)
    collection.objects.link(ob)
    return ob


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
    if trail:
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


def _shapes(st, shape, axes):
    v, _ = shape
    half = st["spin"][:, None] * 0.5
    q = np.concatenate([np.cos(half), axes * np.sin(half)], axis=1)
    local = v[None] * st["size"][:, None, None]
    return (xform.rotate(q[:, None], local) + st["pos"][:, None]).reshape(-1, 3), len(v)


def update(ob, t):
    raw, spec, shape, axes = _spec(ob)
    st = pts.state(spec, t)
    dead = st["alpha"] <= 0
    st["size"] = np.where(dead, 0.0, st["size"])
    if shape is not None:
        co, per = _shapes(st, shape, axes)
    else:
        co, per = _billboards(st, spec["preset"])
    me = ob.data
    if len(me.vertices) != len(co):
        return
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    rgba = np.concatenate([st["color"], st["alpha"][:, None]], axis=1)
    me.attributes[materials.COLOR_ATTR].data.foreach_set("color", np.repeat(rgba, per, axis=0).astype(np.float32).ravel())
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
