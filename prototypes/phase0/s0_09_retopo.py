"""S0-09: defaults for flat text retopology (curve resolution + limited dissolve + beauty triangulation).

Reference = Blender's own fill at resolution_u=12. For each (resolution, angle) we measure
triangles, outline vertices, area error vs reference and whether every hole/stroke survived.
"""
import math
import bpy
import bmesh

CHARS = (
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはまやらわ"   # hiragana 30
    "アイウエオカキクケコサシスセソタチツテト"                         # katakana 20
    "夜明色覚声遠鳴透明終風光影空星雨涙心恋夢響輝闇翼愛世界永遠奇跡願歌鬱"  # kanji 35
    "AaBgQR8@&%"                                                     # latin / digits 10
    "、。！？「"                                                      # punctuation 5
)
FONTS = {
    "gothic": r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
    "mincho": r"C:\Windows\Fonts\yumin.ttf",
}
RESOLUTIONS = (12, 6, 4, 3, 2)
ANGLES = (0.0, 1.0, 3.0, 5.0)


def glyph_bmesh(vfont, ch, resolution):
    cu = bpy.data.curves.new("g", "FONT")
    cu.body, cu.font, cu.size = ch, vfont, 1.0
    cu.fill_mode, cu.resolution_u = "BOTH", resolution
    ob = bpy.data.objects.new("g", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    ob.evaluated_get(dg).to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return bm


def retopo(bm, angle_deg, merge_dist=1e-5):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    if angle_deg > 0:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angle_deg), use_dissolve_boundaries=False,
                                   verts=bm.verts, edges=bm.edges)
    else:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.01), use_dissolve_boundaries=False,
                                   verts=[], edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method="BEAUTY", ngon_method="BEAUTY")
    return bm


def stats(bm):
    bm.edges.ensure_lookup_table()
    boundary = [e for e in bm.edges if len(e.link_faces) == 1]
    # count closed outline loops (outer contours + holes)
    seen, loops = set(), 0
    adj = {}
    for e in boundary:
        for v in e.verts:
            adj.setdefault(v.index, []).append(e.other_vert(v).index)
    for start in adj:
        if start in seen:
            continue
        loops += 1
        stack = [start]
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            stack.extend(adj[v])
    tris = len(bm.faces)
    area = sum(f.calc_area() for f in bm.faces)
    # sliver ratio: share of triangles whose smallest angle is under 5 degrees
    slivers = 0
    for f in bm.faces:
        if len(f.verts) == 3 and min(l.calc_angle() for l in f.loops) < math.radians(5):
            slivers += 1
    return {"tris": tris, "outline_verts": len(adj), "loops": loops, "area": area,
            "sliver_ratio": slivers / max(1, tris)}


def run_grid():
    out = {}
    for fkey, path in FONTS.items():
        vf = bpy.data.fonts.load(path, check_existing=True)
        refs = {}
        for ch in CHARS:
            bm = glyph_bmesh(vf, ch, 12)
            refs[ch] = stats(bm)
            bm.free()
        ref_tris = sum(r["tris"] for r in refs.values())
        rows = []
        for res in RESOLUTIONS:
            for ang in ANGLES:
                tris = verts = broken = 0
                max_area_err = slivers = 0.0
                worst = ""
                for ch in CHARS:
                    bm = retopo(glyph_bmesh(vf, ch, res), ang)
                    s = stats(bm)
                    bm.free()
                    tris += s["tris"]
                    verts += s["outline_verts"]
                    slivers += s["sliver_ratio"]
                    if s["loops"] != refs[ch]["loops"]:
                        broken += 1
                    err = abs(s["area"] - refs[ch]["area"]) / max(1e-9, refs[ch]["area"])
                    if err > max_area_err:
                        max_area_err, worst = err, ch
                rows.append({"res": res, "angle": ang, "tris": tris, "tris_vs_ref": round(tris / ref_tris, 3),
                             "avg_tris": round(tris / len(CHARS), 1), "outline_verts": verts,
                             "broken_glyphs": broken, "max_area_err_pct": round(max_area_err * 100, 2),
                             "worst_char": worst, "avg_sliver_pct": round(slivers / len(CHARS) * 100, 1)})
        out[fkey] = {"ref_tris": ref_tris, "ref_avg_tris": round(ref_tris / len(CHARS), 1),
                     "ref_avg_sliver_pct": round(sum(r["sliver_ratio"] for r in refs.values()) / len(CHARS) * 100, 1),
                     "rows": rows}
    return out


def build_collection(parent, resolution, angle, chars="夢響輝あ遠Ag鬱"):
    """Top row: Blender default fill (res 12). Bottom row: retopo with the chosen defaults."""
    coll = bpy.data.collections.new("S0-09")
    parent.children.link(coll)
    for fi, (fkey, path) in enumerate(FONTS.items()):
        vf = bpy.data.fonts.load(path, check_existing=True)
        for i, ch in enumerate(chars):
            for row, (label, bm) in enumerate((("ref", retopo_ref(vf, ch)),
                                               ("opt", retopo(glyph_bmesh(vf, ch, resolution), angle)))):
                me = bpy.data.meshes.new(f"{fkey}_{label}_{ch}")
                bm.to_mesh(me)
                bm.free()
                ob = bpy.data.objects.new(me.name, me)
                ob.location = (i * 1.3, -(fi * 2 + row) * 1.3 - 12, 0)
                coll.objects.link(ob)
    return coll


def retopo_ref(vf, ch):
    return glyph_bmesh(vf, ch, 12)
