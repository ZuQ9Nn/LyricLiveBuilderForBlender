"""Phase 6 integration test (background Blender): stage objects in the preview, the asset library,
the Unity export and batch build, the emblem, spectrum bars, translations.

  blender --background --factory-startup --python tests/blender/test_phase6.py -- --project <closed Unity project>
"""
import json
import os
import shutil
import sys
import tempfile
import traceback

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]

import lyric_live_builder as llb                                     # noqa: E402
from common import check, draw_panels, failures, font_arg, setup, song, translation_checks  # noqa: E402
from test_phase5 import arg, batch                                   # noqa: E402
from lyric_live_builder.core import bake                             # noqa: E402
from lyric_live_builder.core.parts import gimmicks                   # noqa: E402
from lyric_live_builder.export_unity import exporter, meshbin, unity_locate  # noqa: E402
from lyric_live_builder.preview import gimmick_assets                # noqa: E402
from lyric_live_builder.ui import operators_export, planning, project  # noqa: E402

LYRICS = "[Aメロ]\n朝の木の下で\n星が降ってきた\n猫がいた\n小さな箱\n時計の針\n傘をさす\n雪が溶ける\n名前を呼ぶ\n[サビ]\n鐘が鳴る\n"


def make_library(folder):
    """One tagged asset with a modifier and a colour, away from the origin."""
    path = os.path.join(folder, "objects.blend")
    scene = bpy.data.scenes.new("library")
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(3.0, 1.0, 2.0))
    ob = bpy.context.object
    ob.name = "MyCat"
    ob.modifiers.new("sub", "SUBSURF")
    mat = bpy.data.materials.new("Orange")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1.0, 0.4, 0.05, 1.0)
    ob.data.materials.append(mat)
    ob.asset_mark()
    ob.asset_data.tags.new("猫")
    bpy.data.libraries.write(path, {ob, mat}, fake_user=True)
    bpy.data.objects.remove(ob)
    bpy.data.scenes.remove(scene)
    bpy.data.materials.remove(mat)
    return path


def main():
    unity_project = arg("--project")
    font = font_arg()
    llb.register()
    from lyric_live_builder.core.rng import Rng
    planning.random = lambda: Rng(91)
    work = tempfile.mkdtemp(prefix="llb_phase6_")
    index = gimmick_assets._index_path()
    try:
        # the asset library leaves nothing in the open file
        path = make_library(work)
        before = (len(bpy.data.objects), len(bpy.data.libraries), len(bpy.data.meshes))
        count, tags = gimmick_assets.refresh(work)
        check((count, tags) == (1, 1), f"library indexed ({count} objects, {tags} tags)")
        check((len(bpy.data.objects), len(bpy.data.libraries), len(bpy.data.meshes)) == before, "refresh leaves nothing behind")
        check(gimmick_assets.assets().get("cat", {}).get("name") == "MyCat", "a Japanese tag lands on the dictionary's tag")

        scene, proj = setup(LYRICS, font)
        wav = os.path.join(work, "song.wav")
        song(wav, seconds=50.0)
        bpy.ops.llb.load_audio(filepath=wav)
        for i, ln in enumerate(proj.lines):
            ln.tap_time = 1.0 + i * 3.5
        project.recompute(scene)
        proj.fx.gimmick = 1.0
        proj.fx.spectrum = "all"
        order = ("floor", "sky", "pop", "open", "flip", "wall", "dissolve")
        tags_ = ("tree", "star", "AUTO", "box", "clock", "umbrella", "snow")
        for ln, show, tag in zip(proj.lines, order, tags_):
            ln.gimmick_show, ln.gimmick = show, tag
        proj.lines[7].gimmick, proj.lines[7].gimmick_word = "emblem", "名前"
        bpy.ops.llb.preview_build()
        plan = planning.make_plan(proj)
        check([g["show"] for g in plan.gimmicks][:7] == list(order), "the seven ways of appearing are planned")
        check(plan.gimmicks[2]["source"] == "user" and plan.gimmicks[7]["source"] == "emblem", "user object and emblem found")
        coll = bpy.data.collections["LLB_Gimmicks"]
        by_node = {ob["llb_node"]: ob for ob in coll.objects}
        check(len([k for k in by_node if k.startswith("bar")]) == gimmicks.BARS, "24 spectrum bars in the preview")
        cat = by_node["gim002_obj"]
        v = np.array([x.co for x in cat.data.vertices])
        check(abs(np.ptp(v[:, 2]) - 1.0) < 1e-3 and abs(v[:, 2].min()) < 1e-3 and np.abs(v[:, :2].mean(axis=0)).max() < 0.05,
              "the user's object is 1 unit tall, on the floor, centred")
        check(len(v) > 8 and cat.data.polygons, f"modifiers are applied ({len(v)} vertices)")
        attr = cat.data.color_attributes.get("llb_col")
        check(attr is not None and abs(attr.data[0].color[0] - 1.0) < 0.01 and abs(attr.data[0].color[1] - 0.4) < 0.01,
              "its base colour is painted per vertex")
        check(cat.data.materials[0].name == "LLB_GimmickVC", "it uses the vertex colour material")
        check(len(bpy.data.libraries) == 0, "appending keeps no library link")
        fps = scene.render.fps
        g = plan.gimmicks[0]
        scene.frame_set(scene.frame_start + int((g["start"] + 1.5) * fps))
        ob = by_node["gim000_obj"]
        bpy.context.view_layer.update()
        check(not ob.hide_viewport and abs(ob.matrix_world.translation.length - gimmicks.RADIUS) < 0.1, "the object stands on stage while it is shown")
        scene.frame_set(scene.frame_start + int((g["end"] + 0.5) * fps))
        check(ob.hide_viewport, "and is hidden afterwards")
        emblem = [ob for k, ob in by_node.items() if k.startswith("gim007_g")]
        check(len(emblem) == 2 and all(o.type == "MESH" and len(o.data.vertices) > 8 for o in emblem), "the emblem is 3D letters")

        # export and build (a project without the VRChat SDK)
        st = proj.export
        st.project_path = unity_project
        st.folder_name = "LLB Phase6 Test"
        st.use_mobile = True
        folder = exporter.song_folder(unity_project, st.folder_name)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        unity, _ = operators_export.unity_path(bpy.context)
        check(unity_locate.is_project(unity_project) and unity is not None, "test project and Unity")
        bpy.ops.llb.check_budget()
        budget = json.loads(st.budget)
        check(all(x <= lim for x, lim, _ in budget.values()), f"within the limits {budget}")
        baked = bake.bake(plan, project.metrics(proj), mobile=True)
        sections = [{"index": i, "label": s.label or s.kind, "kind": s.kind, "start": a, "end": b}
                    for i, (s, (a, b)) in enumerate(zip(proj.sections, plan.sections))]
        folder, _ = exporter.export(unity_project, st.folder_name, baked, plan, sections,
                                    lambda role: project.font_paths(proj, role), audio_path=wav,
                                    options=operators_export.export_options(st), version="test")
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            doc = json.load(f)
        with open(os.path.join(folder, "meshes.bin"), "rb") as f:
            blob = f.read()
        entries = {m["key"]: m for m in doc["meshes"]}
        decoded = meshbin.decode(blob, entries["user:MyCat"]["offset"])
        check(decoded[3] is not None and decoded[2].size // 3 <= 1000, f"the user's object exported with colours ({decoded[2].size // 3} triangles)")
        check(sum(1 for key in entries if key.startswith("gimmick:")) >= 7, "built-in shapes exported")
        check(any(c["category"] == "gimmicks" and c["curves"] for c in doc["clips"]), "gimmick clips")
        check(any(m["shader"] == "gimmick" for m in doc["materials"]), "the gimmick material")
        code, log_lines, errors, log = batch(unity, unity_project, folder)
        done = [ln for ln in log_lines if ln.startswith("[LLB] done")]
        check(code == 0 and not errors and done, f"batch build: exit {code} {errors[:3]} {done[-1:]}")
        check("Shader error" not in log, "the shaders compile")
        draw_panels()
        translation_checks()
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if os.path.isfile(index):
            os.remove(index)
    llb.unregister()


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
