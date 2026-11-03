"""mesh_optimizer on its own (P5-01, P5-03): background Blender, imported as a top-level package.

  blender --background --factory-startup --python tests/blender/test_mesh_optimizer.py

100 representative characters × 2 typefaces at the mobile defaults: every hole kept, ≤ 300 triangles
per flat letter (spec §10.3); 3D letters ≤ 1,000. Then the standalone operators on a text object.
"""
import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "lyric_live_builder"), HERE]

import mesh_optimizer                                                # noqa: E402  (the package alone)
from mesh_optimizer import api                                       # noqa: E402
from common import check, failures                                   # noqa: E402

CHARS = ("あいうえおかきくけこさしすせそたちつてとなにぬねのはまやらわ"
         "アイウエオカキクケコサシスセソタチツテト"
         "夜明色覚声遠鳴透明終風光影空星雨涙心恋夢響輝闇翼愛世界永遠奇跡願歌鬱龍"
         "AaBgQR8@&%"
         "、。！？「")
FONTS = {"gothic": r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", "mincho": r"C:\Windows\Fonts\yumin.ttf"}


def text_mesh(vfont, ch, resolution, extrude=0.0):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body, cu.font, cu.size, cu.fill_mode = ch, vfont, 1.0, "BOTH"
    cu.extrude = extrude
    ob = bpy.data.objects.new("t", cu)
    bpy.context.scene.collection.objects.link(ob)
    api.optimize_text_curve(ob, resolution=resolution)
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def main():
    check(len(CHARS) == 100, "100 representative characters")
    mob = api.DEFAULTS["mobile"]
    for name, path in FONTS.items():
        if not os.path.isfile(path):
            print("skip", name)
            continue
        vfont = bpy.data.fonts.load(path, check_existing=True)
        stats = {}
        for kind, depth in (("flat", 0.0), ("solid", 0.15)):
            worst, broken, err, lowered, collapsed, total = 0, [], 0.0, [], [], 0
            for ch in CHARS:
                me, rep = api.fit_text_mesh(lambda res: text_mesh(vfont, ch, res), max_tris=api.LIMITS[kind],
                                            dissolve_angle_deg=mob["angle"], depth=depth)
                if not rep.holes_kept:
                    broken.append(ch)
                if rep.resolution < mob["resolution"]:
                    lowered.append(ch)
                if rep.decimated:
                    collapsed.append(ch)
                worst = max(worst, rep.tris)
                err = max(err, rep.area_error)
                total += rep.tris
                bpy.data.meshes.remove(me)
            check(not broken, f"{name} {kind}: every hole kept {broken}")
            check(worst <= api.LIMITS[kind], f"{name} {kind}: at most {worst} triangles (≤ {api.LIMITS[kind]})")
            check(err < 0.05, f"{name} {kind}: area change at most {err * 100:.2f} %")
            print(f"     {name} {kind}: {total / len(CHARS):.0f} triangles a letter; lower resolution {''.join(lowered)}; "
                  f"collapsed {''.join(collapsed)}")

    # the standalone panel's operators
    mesh_optimizer.register()
    try:
        cu = bpy.data.curves.new("口", "FONT")
        cu.body = "口あ"
        ob = bpy.data.objects.new("Text", cu)
        bpy.context.scene.collection.objects.link(ob)
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        r = bpy.ops.mesh_optimizer.clean_text()
        new = bpy.context.view_layer.objects.active
        check(r == {"FINISHED"} and new.type == "MESH" and new is not ob, "Clean Up Text turns a text object into a mesh")
        check(ob.hide_get() and ob.hide_render, "the text object is kept, hidden")
        cube_a = bpy.data.objects.new("A", new.data.copy())
        cube_b = bpy.data.objects.new("B", new.data.copy())
        for o, col in ((cube_a, (1, 0, 0, 1)), (cube_b, (0, 0, 1, 1))):
            bpy.context.scene.collection.objects.link(o)
            m = bpy.data.materials.new(f"m{o.name}")
            m.use_nodes = True
            next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = col
            o.data.materials.clear()
            o.data.materials.append(m)
        res = api.bake_palette_material([cube_a, cube_b])
        check(len(res.colors) == 2 and cube_a.data.materials[0] == cube_b.data.materials[0], "palette: one material, two colours")
        merged = api.merge_static_objects([cube_a, cube_b])
        check(len(merged) == 1 and len(merged[0].data.polygons) == 2 * len(cube_a.data.polygons), "merge: one object")
        tris = api.decimate(merged[0].data, ratio=0.5)
        check(0 < tris < 2 * len(cube_a.data.polygons), f"decimate: {tris} triangles")
    finally:
        mesh_optimizer.unregister()


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
