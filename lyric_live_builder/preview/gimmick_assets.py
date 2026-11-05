"""The user's stage objects from a Blender asset library (spec §8.3.1, design §8.3).

Refresh reads the tags of every object asset without keeping anything (prototype S0-10); an object
is appended when it is used, baked into one mesh with its colours per vertex, normalized (1 unit
tall, standing on z = 0, centred) and kept as a shared mesh."""
import json
import os
import tempfile

import bpy
import numpy as np

from ..core import synonyms
from . import materials

KEY_PROP = "llb_user"
INDEX = "gimmick_index.json"
COLOR = materials.COLOR_ATTR


def _index_path():
    addon = __package__.rsplit(".", 1)[0]
    try:
        folder = bpy.utils.extension_path_user(addon, create=True)
    except ValueError:                                        # loaded from the source tree (tests)
        folder = tempfile.gettempdir()
    return os.path.join(folder, INDEX)


def library_folder(name):
    lib = next((x for x in bpy.context.preferences.filepaths.asset_libraries if x.name == name), None)
    return bpy.path.abspath(lib.path) if lib else ""


def _blend_files(folder):
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".blend"):
                yield os.path.join(root, f)


def _read(path):
    """[(name, tags)] of the object assets in one file; leaves nothing behind."""
    linked = {os.path.normcase(bpy.path.abspath(x.filepath)) for x in bpy.data.libraries}
    keep = os.path.normcase(path) in linked                   # the user's own link: must not be removed
    with bpy.data.libraries.load(path, link=True, assets_only=True) as (src, dst):
        dst.objects = list(src.objects)
    out, lib = [], None
    for ob in dst.objects:
        if ob is None:
            continue
        lib = ob.library
        out.append((ob.name, [t.name for t in ob.asset_data.tags] if ob.asset_data else []))
    if lib is not None and not keep:
        bpy.data.libraries.remove(lib)
    return out


def refresh(folder):
    """Index the library: {tag: [{file, name}]}. Returns (objects, tags)."""
    index, count = {}, 0
    for path in sorted(_blend_files(folder)):
        try:
            assets = _read(path)
        except (OSError, RuntimeError):
            continue                                          # a damaged or newer file: skip it
        for name, tags in assets:
            count += 1
            for tag in {synonyms.canonical(t) for t in tags}:
                index.setdefault(tag, []).append({"file": path, "name": name})
    with open(_index_path(), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    return count, len(index)


def assets():
    """{tag: {file, name}}: the first asset of each tag whose file still exists."""
    try:
        with open(_index_path(), encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError):
        return {}
    out = {}
    for tag, items in index.items():
        hit = next((x for x in items if os.path.isfile(x["file"])), None)
        if hit:
            out[tag] = hit
    return out


def _texture_of(mat):
    """(pixels (H, W, 4), W, H) of the image behind the Base Color input, or None."""
    node = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat.node_tree else None
    links = node.inputs["Base Color"].links if node else ()
    img = links[0].from_node.image if links and links[0].from_node.type == "TEX_IMAGE" else None
    if img is None or not img.has_data or not img.size[0]:
        return None
    w, h = img.size
    px = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4), w, h


def _base(mat):
    if mat is None:
        return (0.8, 0.8, 0.8)
    node = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if mat.node_tree else None
    return tuple(node.inputs["Base Color"].default_value[:3]) if node else tuple(mat.diffuse_color[:3])


def _paint(me):
    """Materials and base colour textures -> a per-vertex colour attribute (one material for all)."""
    col = np.tile(np.array((0.8, 0.8, 0.8, 1.0), dtype=np.float32), (len(me.vertices), 1))
    uv = None
    if me.uv_layers.active:
        uv = np.empty(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
    textures = {}
    for poly in me.polygons:
        mat = me.materials[poly.material_index] if poly.material_index < len(me.materials) else None
        if mat not in textures:
            textures[mat] = (_texture_of(mat) if mat else None, _base(mat))
        tex, base = textures[mat]
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            rgb = base
            if tex is not None and uv is not None:
                px, w, h = tex
                u, v = uv[li] % 1.0
                rgb = px[min(int(v * h), h - 1), min(int(u * w), w - 1), :3]
            col[me.loops[li].vertex_index, :3] = rgb
    attr = me.color_attributes.new(COLOR, "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", col.reshape(-1))


def _normalize(me):
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    lo, hi = v.min(axis=0), v.max(axis=0)
    v = (v - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) / max(hi[2] - lo[2], 1e-6)
    me.vertices.foreach_set("co", v.reshape(-1))
    me.update()


def mesh(file, name):
    """The normalized shared mesh of one asset, or None when it cannot be read."""
    key = f"{file}|{name}"
    for me in bpy.data.meshes:
        if me.get(KEY_PROP) == key:
            return me
    if not os.path.isfile(file):
        return None
    libraries = set(bpy.data.libraries)
    with bpy.data.libraries.load(file, link=False, assets_only=True) as (src, dst):
        dst.objects = [name] if name in src.objects else []
    ob = dst.objects[0] if dst.objects else None
    for lib in set(bpy.data.libraries) - libraries:           # appended data needs no link back
        bpy.data.libraries.remove(lib)
    if ob is None or ob.type != "MESH":
        if ob is not None:
            bpy.data.objects.remove(ob)
        return None
    scene = bpy.context.scene
    scene.collection.objects.link(ob)
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        me.transform(ob.matrix_world)
    finally:
        source = ob.data
        bpy.data.objects.remove(ob)
        if source.users == 0:
            bpy.data.meshes.remove(source)
    _normalize(me)
    _paint(me)
    appended = [m for m in me.materials if m]
    me.materials.clear()
    for m in appended:
        if m.users == 0:
            bpy.data.materials.remove(m)
    me.materials.append(materials.gimmick_material(True))
    me.name = f"LLB_user_{name}"
    me[KEY_PROP] = key
    return me


def arrays(args, mobile=False, max_tris=1000):
    """(verts, faces, colours (V, 4) linear) for the Unity export, or None. mobile: reduced to max_tris."""
    from ..mesh_optimizer import api as mo
    me = mesh(args["file"], args["name"])
    if me is None:
        return None
    work = me.copy()
    try:
        if mobile:
            mo.decimate(work, target_tris=max_tris)
        v = np.empty(len(work.vertices) * 3)
        work.vertices.foreach_get("co", v)
        col = np.empty(len(work.vertices) * 4, dtype=np.float32)
        attr = work.color_attributes.get(COLOR)
        if attr is not None and len(attr.data) == len(work.vertices):
            attr.data.foreach_get("color", col)
        else:                                                 # the reduction dropped the attribute
            col[:] = 1.0
        return v.reshape(-1, 3), [tuple(p.vertices) for p in work.polygons], col.reshape(-1, 4)
    finally:
        bpy.data.meshes.remove(work)
