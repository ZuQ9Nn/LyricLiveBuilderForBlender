"""BakedScene nodes -> Blender objects."""
import bpy

from ..text import glyphs
from . import materials


def build(baked, collection, font_paths, resolution=6):
    """font_paths(role) -> ordered font files to try for a character. Returns {node id: object}."""
    obs = {}
    mat = materials.text_material()
    for n in baked.nodes:
        data = None
        if n.kind == "glyph":
            src = baked.meshes[n.mesh]
            a = src.args
            path = glyphs.font_for_char(font_paths(a["role"]), a["char"])
            if path is None:
                continue                         # no font has it: leave it out rather than draw tofu
            data = glyphs.glyph_mesh(path, a["char"], src.kind == "glyph3d", a["depth"], a["bevel"], resolution)
            if not data.materials:
                data.materials.append(mat)
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
        collection.objects.link(ob)
        if n.parent and n.parent in obs:
            ob.parent = obs[n.parent]
        if not n.default_active:
            ob.hide_viewport = ob.hide_render = True
        obs[n.id] = ob
    return obs
