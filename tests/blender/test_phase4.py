"""Phase 4 integration test (background Blender, no MCP): export to Unity and build in batch mode.

  blender --background --factory-startup --python tests/blender/test_phase4.py -- --project <closed Unity project>

The project must be closed (batch mode) and have the Timeline package. A throwaway project made with
  Unity.exe -batchmode -quit -createProject <dir>   (then add "com.unity.timeline": "1.7.6" to Packages/manifest.json)
also checks that the build works without the VRChat SDK.
"""
import json
import os
import sys
import time
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]

import lyric_live_builder as llb                                     # noqa: E402
from common import check, failures, font_arg, setup, song, translation_checks  # noqa: E402
from lyric_live_builder.core import bake                             # noqa: E402
from lyric_live_builder.export_unity import exporter, meshbin, unity_locate, unity_run  # noqa: E402
from lyric_live_builder.ui import operators_export, planning, project  # noqa: E402


def arg(name):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return argv[argv.index(name) + 1] if name in argv else ""


def main():
    unity_project = arg("--project")
    font = font_arg()
    llb.register()
    from lyric_live_builder.core.rng import Rng
    planning.random = lambda: Rng(77)
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        scene, proj = setup(f.read(), font)
    wav = os.path.join(bpy.app.tempdir, "llb_phase4_song.wav")
    song(wav, seconds=40.0)
    bpy.ops.llb.load_audio(filepath=wav)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 2.0 + i * 2.4
    project.recompute(scene)
    bpy.ops.llb.omakase()
    proj.lines[2].cuts = "3"                                       # a line in cuts reaches Unity as separate groups
    check(unity_locate.is_project(unity_project), f"test project {unity_project}")
    st = proj.export
    st.project_path = unity_project
    st.folder_name = "LLB Phase4 Test"
    folder = exporter.song_folder(unity_project, st.folder_name)

    # Unity missing: an error, nothing written
    st.unity_path = r"C:\nowhere\Unity.exe"
    if os.path.isdir(folder):
        import shutil
        shutil.rmtree(folder)
    r = bpy.ops.llb.export_unity("EXEC_DEFAULT")
    check(r == {"CANCELLED"} and not os.path.exists(folder), "a missing Unity stops the export before writing")
    st.unity_path = ""
    unity, _ = operators_export.unity_path(bpy.context)
    check(unity is not None, f"Unity 2022.3.22f1 found ({unity})")
    check(not unity_locate.project_is_open(unity_project), "the test project is closed")

    # export (what the operator does before it starts Unity)
    plan = planning.make_plan(proj)
    baked = bake.bake(plan, project.metrics(proj))
    sections = [{"index": i, "label": s.label or s.kind, "kind": s.kind, "start": a, "end": b}
                for i, (s, (a, b)) in enumerate(zip(proj.sections, plan.sections))]
    t0 = time.perf_counter()
    folder, _ = exporter.export(unity_project, st.folder_name, baked, plan, sections,
                                lambda role: project.font_paths(proj, role), audio_path=wav, version="test")
    check(time.perf_counter() - t0 < 30, f"export written in {time.perf_counter() - t0:.1f} s")
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
        doc = json.load(f)
    check(len(doc["clips"]) == len(sections) * 4, f"{len(doc['clips'])} clips = sections × 4")
    with open(os.path.join(folder, "meshes.bin"), "rb") as f:
        blob = f.read()
    ok = all(meshbin.decode(blob, m["offset"])[0].shape[0] > 0 for m in doc["meshes"])
    check(ok and len(doc["meshes"]) > 20, f"{len(doc['meshes'])} meshes readable")
    for rel in ("textures/particles_atlas.png", doc["song"]["audio"], exporter.MARKER,
                "../../Editor/LLBBuilder.cs", "../../Runtime/Shaders/LLB_Dome.shader"):
        check(os.path.isfile(os.path.join(folder, rel)), f"written: {rel}")

    # batch build in the closed project
    rel = os.path.relpath(folder, unity_project).replace("\\", "/")
    job = unity_run.BatchBuild(unity, unity_project, rel)
    t0 = time.perf_counter()
    lines = []
    while True:
        done, code, new = job.poll()
        lines += new
        if done or time.perf_counter() - t0 > 900:
            break
        time.sleep(1.0)
    dt = time.perf_counter() - t0
    with open(job.log, encoding="utf-8", errors="replace") as f:
        log = f.read()
    errors = [ln for ln in log.splitlines() if "[LLB][ERROR]" in ln or "error CS" in ln]
    check(done and code == 0, f"batch build finished with exit code {code} in {dt:.0f} s")
    check(not errors, f"no build errors {errors[:3]}")
    check(any(ln.startswith("[LLB] done") for ln in lines), "the log reports [LLB] done")
    gen = os.path.join(folder, "Generated")
    name = os.path.basename(folder)
    check(os.path.isfile(os.path.join(gen, name + ".prefab")), "prefab created")
    check(os.path.isfile(os.path.join(gen, name + ".playable")), "timeline created")
    clips = [f for f in os.listdir(os.path.join(gen, "Clips")) if f.endswith(".anim")] if os.path.isdir(gen) else []
    check(len(clips) == len(sections) * 4, f"{len(clips)} animation clips")
    check(not os.path.exists(os.path.join(folder, exporter.MARKER)), "the build marker is removed")
    with open(os.path.join(gen, name + ".prefab"), encoding="utf-8") as f:
        prefab = f.read()
    check(all(f"L003{x}_" in prefab for x in ("", "-2", "-3")), "the prefab has a group per cut")
    translation_checks()
    llb.unregister()


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
