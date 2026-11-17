"""Phase 1 integration test (background Blender, no MCP).

  blender --background --factory-startup --python tests/blender/test_phase1.py
"""
import os
import shutil
import sys
import tempfile
import traceback
import wave

import bpy
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

import lyric_live_builder as llb                                   # noqa: E402
from lyric_live_builder.ui import project                         # noqa: E402
from tests.core.test_fontinfo import build_face, write_sfnt        # noqa: E402

TMP = tempfile.mkdtemp(prefix="llb_p1_")
failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def metronome_wav(path, bpm=120.0, seconds=40.0, sr=44100):
    n = int(sr * seconds)
    x = np.zeros(n, dtype=np.float32)
    tn = int(sr * 0.02)
    tone = np.sin(2 * np.pi * 1500 * np.arange(tn) / sr) * np.linspace(1, 0, tn)
    for t in np.arange(0.3, seconds - 0.1, 60.0 / bpm):
        x[int(t * sr):int(t * sr) + tn] += tone * 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def main():
    llb.register()
    llb.unregister()
    llb.register()
    check(hasattr(bpy.types.Scene, "llb"), "register / unregister / register")

    scene = bpy.context.scene
    proj = scene.llb
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        sample = f.read()
    text = bpy.data.texts.new("LLB_Lyrics")
    text.write(sample)
    proj.lyrics_text = text
    bpy.ops.llb.refresh()
    check(len(proj.lines) == 15, f"15 lines parsed ({len(proj.lines)})")
    kinds = [s.kind for s in proj.sections]
    # estimated times leave no room for the empty [間奏] heading yet
    check(proj.sections_from_headings and kinds == ["intro", "verse", "prechorus", "chorus", "verse", "chorus", "outro"],
          f"sections from headings {kinds}")
    check(proj.lines[4].section_index == 3 and proj.lines[0].section_index == 1, "lines belong to their heading's section")
    check(all(a.end == b.start for a, b in zip(proj.sections, proj.sections[1:])), "sections tile without gaps")

    wav = os.path.join(TMP, "metronome.wav")
    metronome_wav(wav)
    bpy.ops.llb.load_audio(filepath=wav)
    check(abs(proj.bpm - 120) <= 1, f"BPM of a 120 BPM metronome ({proj.bpm})")
    strip = scene.sequence_editor.strips.get(project.SONG_STRIP)
    check(strip is not None, "song strip placed")
    want_end = scene.frame_start + int(np.ceil(40.0 * project.fps(scene))) - 1
    check(scene.frame_end == want_end, f"scene length fits the song ({scene.frame_end} == {want_end})")
    check(abs(proj.sections[-1].end - 40.0) < 1e-4, "sections run to the end of the song")

    font = os.path.join(TMP, "test.ttf")
    with open(font, "wb") as f:
        f.write(write_sfnt([build_face()]))
    proj.font_body.filepath = font
    miss = project.missing_chars(proj, "body")
    check("夜" in miss and "あ" not in miss, f"missing characters listed ({len(miss)})")

    from lyric_live_builder.ui import tap_sync
    check(not proj.latency_measured and tap_sync.latency_ms(bpy.context) == 0.0, "unmeasured file uses the preferences value")
    proj.tap_latency_ms = 25.0
    check(proj.latency_measured and tap_sync.latency_ms(bpy.context) == 25.0, "a hand-entered latency is used")

    for i, ln in enumerate(proj.lines):
        ln.tap_time = 1.0 + i * 2.0 + (10.0 if i >= 8 else 0.0)      # 10 s instrumental after the chorus
    project.set_line_markers(scene, range(len(proj.lines)))
    project.recompute(scene)
    check(proj.lines[3].start == 7.0 and proj.lines[3].source == "tap", "tap times become line starts")
    kinds = [s.kind for s in proj.sections]
    check(kinds == ["intro", "verse", "prechorus", "chorus", "interlude", "verse", "chorus", "outro"],
          f"the empty [間奏] heading gets the instrumental gap {kinds}")
    check(not any(m.select for m in scene.timeline_markers), "line markers are created unselected")
    scene.timeline_markers.new(project.marker_name(40), frame=500)       # left over from longer lyrics
    project.recompute(scene)
    check(scene.timeline_markers.get(project.marker_name(40)) is None, "markers of lines that no longer exist are removed")
    m = scene.timeline_markers.get(project.marker_name(3))
    m.frame += 12
    n = bpy.ops.llb.import_markers()
    check(abs(proj.lines[3].start - (7.0 + 12 / project.fps(scene))) < 1e-6 and proj.lines[2].start == 5.0,
          "moved marker is imported, others keep their sub-frame time")
    proj.lines[5].use_manual = True
    proj.lines[5].manual_start = 12.345
    check(abs(proj.lines[5].start - 12.345) < 1e-6 and proj.lines[5].source == "manual", "manual time wins over the tap")
    # insert a line at the top: taps, manual times and markers follow their lines
    before = [(ln.text, ln.tap_time, ln.use_manual) for ln in proj.lines]
    proj.lyrics_text.from_string(proj.lyrics_text.as_string().replace("[A]\n", "[A]\n挿入した行\n", 1))
    bpy.ops.llb.refresh()
    after = [(ln.text, ln.tap_time, ln.use_manual) for ln in proj.lines]
    check(after[0] == ("挿入した行", -1.0, False) and after[1:] == before, "inserted line: times stay with their lines")
    m = scene.timeline_markers.get(project.marker_name(4))
    check(m is not None and m.frame == scene.frame_start + round(proj.lines[4].tap_time * project.fps(scene)),
          "markers renumbered after the insert")
    proj.lyrics_text.from_string(proj.lyrics_text.as_string().replace("挿入した行\n", "", 1))
    bpy.ops.llb.refresh()
    check([(ln.text, ln.tap_time, ln.use_manual) for ln in proj.lines] == before, "removing it restores the numbering")
    heading_kind = proj.sections[2].kind
    proj.sections[2].kind = "bridge"                   # as a file from an earlier version set it by hand
    bpy.ops.llb.refresh()
    check(proj.sections[2].kind == heading_kind and not proj.sections[2].user_kind,
          "the kind comes from the headings again on a refresh (not set by hand any more)")

    blend = os.path.join(TMP, "p1.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    bpy.ops.wm.read_homefile(use_factory_startup=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    proj = bpy.context.scene.llb
    check(proj.lyrics_text is not None and proj.lyrics_text.as_string().startswith("# LyricLive"), "lyrics restored")
    check(proj.font_body.filepath == font and proj.audio_path == wav, "font and song paths restored")
    check(abs(proj.bpm - 120) <= 1 and len(proj.lines) == 15, "BPM and lines restored")
    check(abs(proj.lines[3].tap_time - (7.0 + 12 / project.fps(bpy.context.scene))) < 1e-6 and proj.lines[5].use_manual,
          "taps and manual times restored")

    proj.lyrics_text.from_string("\n".join(l for l in sample.splitlines() if not l.startswith("[") or l.startswith("[ti")))
    bpy.ops.llb.refresh()
    kinds = [s.kind for s in proj.sections]
    check(not proj.sections_from_headings and "chorus" in kinds and "bridge" not in kinds,
          f"sections estimated without headings, old hand-set kind dropped ({kinds})")

    bpy.context.preferences.view.language = "ja_JP"
    bpy.context.preferences.view.use_translate_interface = True
    tr = bpy.app.translations.pgettext_iface("Lyric Lines")
    check(tr == "歌詞の行", f"Japanese translation ({tr})")
    bpy.context.preferences.view.language = "en_US"

    # the pages at the top of the LyricLive tab: each panel shows on its own page only
    from lyric_live_builder.ui import panels
    ctx = type("Ctx", (), {"scene": bpy.context.scene})()
    shown = {}
    for page in ("setup", "compose", "output"):
        proj.ui_page = page
        shown[page] = {c.__name__ for c in panels.CLASSES
                       if issubclass(c, bpy.types.Panel) and (not hasattr(c, "poll") or c.poll(ctx))
                       and not getattr(c, "bl_parent_id", "")}
    every = {"LLB_PT_pages", "LLB_PT_generate"}                      # Generate is on every page (spec §11)
    check(shown["setup"] == every | {"LLB_PT_lyrics", "LLB_PT_fonts", "LLB_PT_song", "LLB_PT_sync"}
          and shown["compose"] == every | {"LLB_PT_omakase", "LLB_PT_trial", "LLB_PT_sections", "LLB_PT_lines"}
          and shown["output"] == every | {"LLB_PT_effects", "LLB_PT_preview", "LLB_PT_export"}, f"pages {shown}")

    llb.unregister()
    check(not hasattr(bpy.types.Scene, "llb"), "unregister")


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
