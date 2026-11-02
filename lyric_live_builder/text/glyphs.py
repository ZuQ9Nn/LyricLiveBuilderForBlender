"""Characters -> meshes (2D flat or 3D extruded), shared per (font, char, settings) (design §6.2).

A glyph mesh is 1 em tall, centred on the middle of its advance and the middle of the font's
ascender..descender, and stands in the XZ plane facing -Y (toward the viewer).
"""
import math
import os

import bpy
from mathutils import Matrix

from . import fontinfo

KEY_PROP = "llb_glyph"
_cache = {}                      # key -> mesh name (validated against bpy.data on use)


def glyph_key(font_path, ch, is_3d, depth, bevel, resolution):
    path = os.path.normcase(os.path.abspath(font_path))
    return f"{path}|{ord(ch)}|{int(is_3d)}|{depth:.3f}|{bevel:.3f}|{resolution}"


def _find(key):
    name = _cache.get(key)
    me = bpy.data.meshes.get(name) if name else None
    if me is not None and me.get(KEY_PROP) == key:
        return me
    for me in bpy.data.meshes:                 # meshes saved in the .blend from an earlier session
        if me.get(KEY_PROP) == key:
            _cache[key] = me.name
            return me
    return None


def glyph_mesh(font_path, ch, is_3d=False, depth=0.15, bevel=0.02, resolution=6):
    """The shared mesh for one character (created on first use)."""
    key = glyph_key(font_path, ch, is_3d, depth, bevel, resolution)
    me = _find(key)
    if me is not None:
        return me
    info = fontinfo.load(font_path)
    vfont = bpy.data.fonts.load(font_path, check_existing=True)
    cu = bpy.data.curves.new("llb_glyph_tmp", "FONT")
    cu.body = ch
    cu.font = vfont
    cu.size = 1.0 / info.blender_units_per_em            # 1 em == 1 unit (prototype S0-01)
    cu.align_x = "LEFT"
    cu.align_y = "TOP_BASELINE"
    cu.fill_mode = "BOTH"
    cu.resolution_u = resolution
    if is_3d:
        cu.extrude = depth / 2
        cu.bevel_depth = bevel
        cu.bevel_resolution = 1
    ob = bpy.data.objects.new("llb_glyph_tmp", cu)
    bpy.context.scene.collection.objects.link(ob)
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
    asc = info.ascender if info.ascender is not None else 0.88 * info.units_per_em
    desc = info.descender if info.descender is not None else -0.12 * info.units_per_em
    centre = Matrix.Translation((-info.advance_em(ch) / 2, -(asc + desc) / 2 / info.units_per_em, 0.0))
    me.transform(Matrix.Rotation(math.pi / 2, 4, "X") @ centre)   # XY plane facing +Z -> XZ facing -Y
    me.name = f"LLB_glyph_{ch}"
    me[KEY_PROP] = key
    _cache[key] = me.name
    return me


def font_for_char(paths, ch):
    """First font path in paths that has the character (fallback order), or None."""
    for p in paths:
        if p and os.path.isfile(p):
            try:
                if fontinfo.load(p).has_char(ch):
                    return p
            except (OSError, ValueError):
                continue
    return None
