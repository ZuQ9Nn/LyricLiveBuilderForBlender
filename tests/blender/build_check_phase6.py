"""Builds tests/manual/check_phase6.blend for the reviewer (background Blender).

  blender --background --factory-startup --python tests/blender/build_check_phase6.py -- --project <Unity project>

Lyrics full of keywords, a 70 s metronome as the song (tests/manual/metronome_120bpm_70s.wav),
Windows fonts, one fixed proposal. Lines 1-7 use the seven ways of appearing in order, line 8 an
emblem; spectrum bars in choruses. The Unity Export panel points at the given project (song folder
"LLB_Phase6_Check") with mobile optimisation and Udon sync on. The add-on is loaded from the source tree.
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]

import lyric_live_builder as llb                                     # noqa: E402
from build_check_phase5 import FONTS, MANUAL, metronome              # noqa: E402

LYRICS = """[Aメロ]
朝の木の下で待っていた
空から星が降ってきた
心に月を浮かべて
小さな箱を開けてみる
時計の針が止まる頃
傘をさして歩いた
雪は静かに溶けていく
名前を呼ぶよ

[サビ]
光の中で鐘が鳴る!
宝石みたいな夜に
ありがとう
花を抱えて走るよ
"""


def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    llb.register()
    scene = bpy.context.scene
    scene.render.fps = 60
    proj = scene.llb
    text = bpy.data.texts.new("LLB_Lyrics")
    text.write(LYRICS)
    proj.lyrics_text = text
    for role, path in FONTS.items():
        if os.path.isfile(path):
            proj.font(role).filepath = path
    song = os.path.join(MANUAL, "metronome_120bpm_70s.wav")
    if not os.path.isfile(song):
        metronome(song)
    bpy.ops.llb.load_audio(filepath=song)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 2.0 + i * 4.0
    bpy.ops.llb.refresh()
    from lyric_live_builder.ui import planning
    planning.push_history(proj, planning.state(proj))
    st = dict(planning.state(proj), mood="emotional", style="noir", seed=2)
    st["fx"] = dict(st["fx"], gimmick=1.0, spectrum="chorus")
    planning.apply_state(proj, st)
    planning.push_history(proj, st)
    scene.view_settings.view_transform = "Standard"
    shows = ("floor", "sky", "pop", "open", "flip", "wall", "dissolve")
    objects = ("tree", "star", "moon", "box", "clock", "umbrella", "snow")
    for ln, show, obj in zip(proj.lines, shows, objects):
        ln.gimmick, ln.gimmick_show = obj, show
    proj.lines[7].gimmick, proj.lines[7].gimmick_word = "emblem", "名前"
    bpy.ops.llb.preview_build()
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--project" in argv:
        proj.export.project_path = argv[argv.index("--project") + 1]
    proj.export.folder_name = "LLB_Phase6_Check"
    proj.export.use_mobile = proj.export.use_udon_sync = True
    out = os.path.join(MANUAL, "check_phase6.blend")
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("SAVED", out)


if __name__ == "__main__":
    main()
