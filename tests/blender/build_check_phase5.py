"""Builds tests/manual/check_phase5.blend for the reviewer (background Blender).

  blender --background --factory-startup --python tests/blender/build_check_phase5.py -- --project <Unity project>

Sample lyrics, a 70 s metronome as the song (tests/manual/metronome_120bpm_70s.wav), Windows
fonts, one fixed proposal (emotional / noir) built like Make It for Me, Standard colours, and the
Unity Export panel pointed at the given project (song folder "LLB_Phase5_Check") with mobile
optimisation, TextMesh Pro and Udon sync on; line 3 is a 3D line kept until its section ends.
The add-on is loaded from the source tree.
"""
import os
import sys
import wave

import bpy
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
import lyric_live_builder as llb  # noqa: E402

MANUAL = os.path.join(ROOT, "tests", "manual")
FONTS = {"body": r"C:\Windows\Fonts\BIZ-UDGothicR.ttc", "display": r"C:\Windows\Fonts\BIZ-UDGothicB.ttc",
         "serif": r"C:\Windows\Fonts\yumin.ttf"}


def metronome(path, bpm=120.0, seconds=70.0, sr=44100):
    x = np.zeros(int(sr * seconds), dtype=np.float32)
    tn = int(sr * 0.02)
    tone = np.sin(2 * np.pi * 1500 * np.arange(tn) / sr) * np.linspace(1, 0, tn)
    for k, t in enumerate(np.arange(0.5, seconds - 0.1, 60.0 / bpm)):
        x[int(t * sr):int(t * sr) + tn] += tone * (0.8 if k % 4 == 0 else 0.45)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    llb.register()
    scene = bpy.context.scene
    scene.render.fps = 60
    proj = scene.llb
    with open(os.path.join(MANUAL, "lyrics_sample.txt"), encoding="utf-8") as f:
        text = bpy.data.texts.new("LLB_Lyrics")
        text.write(f.read())
    proj.lyrics_text = text
    for role, path in FONTS.items():
        if os.path.isfile(path):
            proj.font(role).filepath = path
    song = os.path.join(MANUAL, "metronome_120bpm_70s.wav")
    metronome(song)
    bpy.ops.llb.load_audio(filepath=song)
    # sing a line every two bars after a short intro, with an instrumental gap at [間奏]
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 4.0 + i * 4.0 + (8.0 if i >= 8 else 0.0)
    bpy.ops.llb.refresh()
    from lyric_live_builder.ui import planning
    planning.push_history(proj, planning.state(proj))
    st = dict(planning.state(proj), mood="emotional", style="noir", seed=2)
    st["fx"] = dict(st["fx"], world_switch=0.9, particles=0.7)
    planning.apply_state(proj, st)
    planning.push_history(proj, st)
    scene.view_settings.view_transform = "Standard"
    proj.lines[2].is_3d = True                       # one 3D line stays a mesh when the others become TextMesh Pro
    proj.lines[2].persist = "section"
    bpy.ops.llb.preview_build()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--project" in argv:
        proj.export.project_path = argv[argv.index("--project") + 1]
    proj.export.folder_name = "LLB_Phase5_Check"
    proj.export.use_mobile = proj.export.use_tmp = proj.export.use_udon_sync = True
    out = os.path.join(MANUAL, "check_phase5.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)


main()
