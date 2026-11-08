"""Phase 2 integration test (background Blender, no MCP).

  blender --background --factory-startup --python tests/blender/test_phase2.py [-- --font <ttf/otf/ttc>]

Needs a real font (glyph outlines); defaults to a Windows Japanese font when none is given.
"""
import math
import os
import sys
import time
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]

import lyric_live_builder as llb                                     # noqa: E402
from common import check, failures, font_arg, setup, text_objects, translation_checks  # noqa: E402
from lyric_live_builder.core import bake, model                      # noqa: E402
from lyric_live_builder.preview import scene as preview_scene        # noqa: E402
from lyric_live_builder.ui import planning, project                  # noqa: E402


def baked_now(proj):
    plan = planning.make_plan(proj)
    return plan, bake.bake(plan, project.metrics(proj))


def objects_by_node():
    return text_objects()


def frame_of(scene, t):
    return scene.frame_start + t * scene.render.fps / scene.render.fps_base


def check_against_core(scene, baked, times):
    """Blender's evaluated positions / visibility == core's world_positions."""
    obs = objects_by_node()
    # where the line stands: its glyphs, not the slice's band copies or the effect planes (design §5.6)
    glyphs = {n.id for n in baked.nodes if n.kind == "glyph" and not bake.is_band_copy(n.id)}
    worst, vis_bad = 0.0, 0
    for t in times:
        f = frame_of(scene, t)
        scene.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
        want = bake.world_positions(baked, t)
        for nid, ob in obs.items():
            if ob.type != "MESH" or nid not in glyphs:
                continue
            shown = not ob.hide_viewport
            if shown != (nid in want):
                vis_bad += 1
                print(f"     visibility t={t:.3f} {nid} blender={shown} core={nid in want}")
                continue
            if shown:
                worst = max(worst, float(np.linalg.norm(np.array(ob.matrix_world.translation) - want[nid])))
    return worst, vis_bad


def main():
    font = font_arg()
    llb.register()
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        sample = f.read()
    scene, proj = setup(sample, font)
    proj.lines[0].is_3d = True
    proj.lines[0].layout = "slanted_wall"
    proj.lines[2].persist = "section"
    proj.lines[3].layout = "slanted_wall"                 # 3D-only on a flat line: ignored

    r = bpy.ops.llb.preview_build()
    check(r == {"FINISHED"}, "generate")
    plan, baked = baked_now(proj)
    obs = objects_by_node()
    glyph_nodes = [n for n in baked.nodes if n.kind == "glyph"]
    glyph_ids = {n.id for n in glyph_nodes}
    meshes = [ob for nid, ob in obs.items() if ob.type == "MESH" and nid in glyph_ids]
    check(len(meshes) == len(glyph_nodes) > 100, f"one object per glyph ({len(meshes)})")
    check(scene.camera and scene.camera.name == preview_scene.CAMERA_OBJECT, "audience camera is the scene camera")
    check(plan.lines[0].layout == "slanted_wall" and plan.lines[3].layout != "slanted_wall", "3D-only layout only on the 3D line")
    thick = [ob.data.dimensions if hasattr(ob.data, "dimensions") else None for ob in meshes]
    ys = {ob["llb_node"].split("_")[0]: max(v.co.y for v in ob.data.vertices) - min(v.co.y for v in ob.data.vertices) for ob in meshes}
    check(ys["line000"] > 0.1 and all(v < 1e-6 for k, v in ys.items() if k != "line000"), "only the 3D line is thick")
    line2 = plan.lines[2]
    sec_end = proj.sections[proj.lines[2].section_index].end
    check(line2.persist and abs(line2.end - sec_end) < 1e-6, "kept line stays until its section ends")

    times = np.arange(0.0137, proj.duration, 0.37)     # off the exact key times (float32 keys)
    worst, vis_bad = check_against_core(scene, baked, times)
    check(vis_bad == 0, f"visibility in Blender matches the plan ({vis_bad} mismatches)")
    check(worst < 0.003, f"Blender positions match the core within 3 mm (worst {worst * 1000:.2f} mm)")

    eye = np.array([0, 0, model.EYE_HEIGHT])
    near = min(np.linalg.norm(p - eye) for t in times for p in bake.world_positions(baked, t).values())
    check(near >= model.MIN_EYE_DISTANCE - 1e-6, f"nothing closer than 0.6 m to the eye ({near:.2f} m)")

    # deterministic: generate again, same transforms
    def shown_at(t):
        scene.frame_set(int(frame_of(scene, t)))
        return {nid: tuple(round(x, 6) for x in ob.matrix_world.translation)
                for nid, ob in objects_by_node().items() if not ob.hide_viewport}
    before = [shown_at(t) for t in (3.0, 6.0, 9.0)]
    bpy.ops.llb.preview_build()
    after = [shown_at(t) for t in (3.0, 6.0, 9.0)]
    check(all(before), "something is visible at 3, 6 and 9 s")
    check(before == after, "same settings give the same result")
    proj.seed += 1
    bpy.ops.llb.preview_build()
    plan2, _ = baked_now(proj)
    check([x.layout for x in plan2.lines] != [x.layout for x in plan.lines], "another seed gives another result")

    # a four minute song: 60 lines
    long = "\n".join(["[A]"] + [f"{i}番目の歌詞の行をここに書く" for i in range(60)])
    scene, proj = setup(long, font)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 2.0 + i * 4.0
    project.recompute(scene)
    t0 = time.perf_counter()
    bpy.ops.llb.preview_build()
    dt = time.perf_counter() - t0
    check(dt < 30.0, f"4 minute song generated in {dt:.1f} s (< 30 s)")

    translation_checks()
    bpy.ops.llb.preview_clear()
    check(not [ob for ob in bpy.data.collections[preview_scene.ROOT].all_objects if ob.type == "MESH"], "delete")
    llb.unregister()


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
