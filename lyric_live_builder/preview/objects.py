"""BakedScene nodes -> Blender objects."""
import bpy

from ..core import meshes
from ..text import glyphs
from . import gimmick_assets, materials, particles

BUILTIN = "llb_builtin"


def _builtin_mesh(key):
    """A mesh from core.meshes, shared between previews (tagged with its key)."""
    for me in bpy.data.meshes:
        if me.get(BUILTIN) == key:
            return me
    v, f = meshes.build(key)
    me = bpy.data.meshes.new(f"LLB_{key.replace(':', '_')}")
    me.from_pydata(v.tolist(), [], [tuple(x) for x in f])
    me[BUILTIN] = key
    return me


MATERIALS = {"text": materials.text_material, "far": materials.far_material, "glow": materials.glow_material,
             "gimmick": materials.gimmick_material}


def build(baked, collections, font_paths, resolution=6, panorama="", dome=materials.DOME):
    """collections: {category: collection}; font_paths(role) -> font files to try. Returns {node id: object}."""
    obs = {}
    emitters = {e["node"]: e["spec"] for e in baked.emitters}
    for n in baked.nodes:
        coll = collections[n.category]
        data = None
        if n.kind == "emitter":
            ob = particles.create(f"LLB_{n.name}", emitters[n.id], coll)
            ob["llb_node"] = n.id
            ob.hide_viewport = ob.hide_render = not n.default_active
            obs[n.id] = ob
            continue
        if n.kind == "glyph":
            src = baked.meshes[n.mesh]
            a = src.args
            path = glyphs.font_for_char(font_paths(a["role"]), a["char"])
            if path is None:
                continue                         # no font has it: leave it out rather than draw tofu
            data = glyphs.glyph_mesh(path, a["char"], src.kind == "glyph3d", a["depth"], a["bevel"], resolution)
        elif n.mesh.startswith("user:"):
            args = baked.meshes[n.mesh].args
            data = gimmick_assets.mesh(args["file"], args["name"])
        elif n.mesh:
            data = _builtin_mesh(n.mesh)
        if data is not None:
            # the dome material is refreshed every time (the panorama may have changed)
            mat = materials.dome_material(panorama, dome) if n.material == "dome" else None
            if not data.materials:
                data.materials.append(mat or MATERIALS[n.material]())
        ob = bpy.data.objects.new(f"LLB_{n.name}", data)
        if data is None:
            ob.empty_display_type = "PLAIN_AXES"
            ob.empty_display_size = 0.05
        ob.rotation_mode = "QUATERNION"
        ob.location = n.loc
        ob.rotation_quaternion = n.rot
        ob.scale = n.scale
        ob.color = n.color
        ob["llb_node"] = n.id
        if n.kind == "dome":
            ob.hide_select = True                # a 60 m sphere around everything: keep clicks for the rest
        coll.objects.link(ob)
        if n.parent and n.parent in obs:
            ob.parent = obs[n.parent]
        if not n.default_active:
            ob.hide_viewport = ob.hide_render = True
        obs[n.id] = ob
    return obs
