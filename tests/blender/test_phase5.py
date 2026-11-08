"""Phase 5 integration test (background Blender): mobile export + batch build, budget check, option checks.

  blender --background --factory-startup --python tests/blender/test_phase5.py -- --project <closed Unity project>

Use the throwaway project of test_phase4 (no VRChat SDK, no TextMesh Pro): the build scripts must still
compile there; TextMesh Pro is refused before writing; Udon sync is skipped with a warning.
TextMesh Pro and Udon in a VRChat project are checked in the editor (docs/04, phase 5).
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


def batch(unity, project_dir, folder):
    rel = os.path.relpath(folder, project_dir).replace("\\", "/")
    job = unity_run.BatchBuild(unity, project_dir, rel)
    t0, lines = time.perf_counter(), []
    while True:
        done, code, new = job.poll()
        lines += new
        if done or time.perf_counter() - t0 > 900:
            break
        time.sleep(1.0)
    with open(job.log, encoding="utf-8", errors="replace") as f:
        log = f.read()
    # a first compile may run before newly copied scripts are imported (batch start-up); it is followed
    # by a clean one, so compile errors only count when no build completed
    done = any(ln.startswith("[LLB] done") for ln in lines)
    errors = [ln for ln in log.splitlines() if "[LLB][ERROR]" in ln or ("error CS" in ln and not done)]
    return code, lines, errors, log


def main():
    unity_project = arg("--project")
    font = font_arg()
    llb.register()
    from lyric_live_builder.core.rng import Rng
    planning.random = lambda: Rng(91)
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        scene, proj = setup(f.read(), font)
    wav = os.path.join(bpy.app.tempdir, "llb_phase5_song.wav")
    song(wav, seconds=40.0)
    bpy.ops.llb.load_audio(filepath=wav)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 2.0 + i * 2.4
        ln.hold = "still"                                  # every line qualifies for a line mesh
    project.recompute(scene)
    bpy.ops.llb.omakase()
    for ln in proj.lines:
        ln.hold = "still"
    st = proj.export
    st.project_path = unity_project
    st.folder_name = "LLB Phase5 Test"
    st.use_mobile = True
    unity, _ = operators_export.unity_path(bpy.context)
    check(unity_locate.is_project(unity_project) and unity is not None, "test project and Unity")
    folder = exporter.song_folder(unity_project, st.folder_name)

    # budget check: normal vs mobile
    st.use_mobile = False
    bpy.ops.llb.check_budget()
    normal = json.loads(st.budget)
    st.use_mobile = True
    bpy.ops.llb.check_budget()
    mobile = json.loads(st.budget)
    check(all(v <= lim for v, lim, _ in mobile.values()), f"mobile export within the limits {mobile}")
    check(mobile["letter_flat"][0] <= normal["letter_flat"][0] and mobile["particles"][0] < normal["particles"][0]
          and mobile["materials"][0] <= normal["materials"][0],                  # fewer only when the show has 3D particles
          f"mobile lowers letters and particles, never adds materials {normal} {mobile}")

    # TextMesh Pro in a project without the package: refused before writing
    import shutil
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    st.use_tmp = True
    r = bpy.ops.llb.export_unity("EXEC_DEFAULT")
    check(r == {"CANCELLED"} and not os.path.exists(folder), "TextMesh Pro without the package stops before writing")
    st.use_tmp = False

    # mobile + Udon sync (no UdonSharp here: built without it, with a warning)
    st.use_udon_sync = True
    plan = planning.make_plan(proj)
    baked = bake.bake(plan, project.metrics(proj), mobile=True)
    sections = [{"index": i, "label": s.label or s.kind, "kind": s.kind, "start": a, "end": b}
                for i, (s, (a, b)) in enumerate(zip(proj.sections, plan.sections))]
    folder, _ = exporter.export(unity_project, st.folder_name, baked, plan, sections,
                                lambda role: project.font_paths(proj, role), audio_path=wav,
                                options=operators_export.export_options(st), version="test")
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
        doc = json.load(f)
    lines = [n for n in doc["nodes"] if n["kind"] == "line_mesh"]
    check(len(lines) >= 5, f"{len(lines)} merged line meshes")
    with open(os.path.join(folder, "meshes.bin"), "rb") as f:
        blob = f.read()
    entries = {m["key"]: m for m in doc["meshes"]}
    coloured = all(meshbin.decode(blob, entries[n["mesh"]]["offset"])[3] is not None for n in lines if n["mesh"] in entries)
    check(coloured, "line meshes carry the letter colours per vertex")
    check(len([m for m in doc["materials"] if m["shader"] == "text"]) == 1, "one text material")
    code, log_lines, errors, log = batch(unity, unity_project, folder)
    check(code == 0 and not errors, f"batch build without TextMesh Pro / UdonSharp packages: exit {code} {errors[:3]}")
    done = [ln for ln in log_lines if ln.startswith("[LLB] done")]
    check(done and "udon=unavailable" in done[-1], f"built without Udon sync ({done[-1] if done else '-'})")
    check("UdonSharp is not in the project" in log, "a warning says why")
    translation_checks()
    llb.unregister()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        failures.append("exception")
    print("RESULT", "PASS" if not failures else f"FAIL {failures}")
    sys.exit(1 if failures else 0)
