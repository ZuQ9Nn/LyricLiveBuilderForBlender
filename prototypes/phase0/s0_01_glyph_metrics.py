"""S0-01: relation between Blender text size and font em / hmtx advances.

measure(): returns, per font, the scale k (Blender units per em at size 1) and the
max deviation between Blender's own string layout and a layout built from hmtx advances.
build_collection(): adds a visual check (Blender layout vs per-glyph layout) to the scene.
"""
import bpy
from fontinfo_proto import FontInfo

FONTS = {
    "gothic_ttc": r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
    "mincho_ttf": r"C:\Windows\Fonts\yumin.ttf",
    "latin_ttf": r"C:\Windows\Fonts\arial.ttf",
}
SAMPLE = {
    "gothic_ttc": "夜明けの色をAg覚えてる、ー",
    "mincho_ttf": "ほどけた声が遠くでLight",
    "latin_ttf": "Feel the light AVA",
}


def _text_obj(name, body, vfont, coll):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.font = vfont
    cu.size = 1.0
    cu.align_x = "LEFT"
    cu.align_y = "TOP_BASELINE"
    cu.fill_mode = "BOTH"
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    return ob


def _bbox_x(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    ob.evaluated_get(dg).to_mesh_clear()
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def measure():
    tmp = bpy.data.collections.new("_s0_01_tmp")
    bpy.context.scene.collection.children.link(tmp)
    out = {}
    for key, path in FONTS.items():
        vf = bpy.data.fonts.load(path, check_existing=True)
        fi = FontInfo(path)
        ref = _bbox_x(_text_obj("ref", "H", vf, tmp))
        # pen position after each prefix, measured by Blender: xmax(P + "H") - xmax("H")
        text = SAMPLE[key]
        dev, k_samples, pen_fi = 0.0, [], 0.0
        for i in range(1, len(text) + 1):
            prefix = text[:i]
            pen_fi += fi.advance_em(prefix[-1])
            bb = _bbox_x(_text_obj("p", prefix + "H", vf, tmp))
            pen_bl = bb[1] - ref[1]
            k_samples.append(pen_bl / pen_fi)
        k = sum(k_samples) / len(k_samples)
        pen_fi = 0.0
        for i in range(1, len(text) + 1):
            pen_fi += fi.advance_em(text[i - 1])
            bb = _bbox_x(_text_obj("p", text[:i] + "H", vf, tmp))
            dev = max(dev, abs((bb[1] - ref[1]) - pen_fi * k))
        out[key] = {
            "units_per_em": fi.units_per_em,
            "k_blender_per_em": round(k, 5),
            "k_from_head_bbox": round(fi.blender_units_per_em, 5),
            "k_spread": round(max(k_samples) - min(k_samples), 5),
            "max_dev_em": round(dev / k, 5),
            "H_ymin_ymax": [round(ref[2], 4), round(ref[3], 4)],
            "os2_asc_desc_em": [fi.ascender / fi.units_per_em, fi.descender / fi.units_per_em],
        }
    for ob in list(tmp.objects):
        bpy.data.curves.remove(ob.data)
    bpy.data.collections.remove(tmp)
    return out


def build_collection(parent):
    """Row per font: Blender's own layout (white) and our hmtx layout (orange) just below.
    The orange row uses only fontinfo (hmtx + head bbox), no measurement."""
    coll = bpy.data.collections.new("S0-01")
    parent.children.link(coll)
    white = _mat("s0_white", (1, 1, 1, 1))
    orange = _mat("s0_orange", (1, 0.45, 0.05, 1))
    for row, (key, path) in enumerate(FONTS.items()):
        vf = bpy.data.fonts.load(path, check_existing=True)
        fi = FontInfo(path)
        k = fi.blender_units_per_em
        y = -row * 3.0
        full = _text_obj(f"{key}_blender", SAMPLE[key], vf, coll)
        full.location = (0, y, 0)
        full.data.materials.append(white)
        pen = 0.0
        for i, ch in enumerate(SAMPLE[key]):
            g = _text_obj(f"{key}_glyph_{i:02d}", ch, vf, coll)
            g.location = (pen * k, y - 1.3, 0)
            g.data.materials.append(orange)
            pen += fi.advance_em(ch)
    return coll


def _mat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m
