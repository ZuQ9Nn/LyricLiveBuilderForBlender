"""Trial views, Before / After (spec §6.3). GUI Blender: 3D views, playback and timers need it.

  blender --factory-startup --python tests/blender/test_trial.py -- <result file> [--font <file>]
"""
import os
import re
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [ROOT, HERE]
OUT = sys.argv[sys.argv.index("--") + 1]

import lyric_live_builder as llb                                     # noqa: E402
from common import font_arg                                          # noqa: E402
from lyric_live_builder.ui import planning, trial                    # noqa: E402

log, failures = [], []


def check(ok, msg):
    log.append(("OK   " if ok else "FAIL ") + msg)
    if not ok:
        failures.append(msg)
    with open(OUT, "w", encoding="utf-8") as f:                       # kept up to date: a crash leaves the log
        f.write("\n".join(log))


def finish():
    log.append("RESULT " + ("PASS" if not failures else f"FAIL {failures}"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    bpy.app.timers.register(quit_blender, first_interval=0.2)


def quit_blender():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.wm.quit_blender()


def sig(root):
    """What a root shows: node ids and every key, independent of object names."""
    coll = bpy.data.collections.get(root)
    out = []
    for ob in (coll.all_objects if coll else ()):
        keys = []
        ad = ob.animation_data
        if ad and ad.action:
            for layer in ad.action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for fc in bag.fcurves:
                            keys.append((fc.data_path, fc.array_index,
                                         tuple(round(v, 4) for kp in fc.keyframe_points for v in kp.co)))
        out.append((ob.get("llb_node", ""), tuple(sorted(keys))))           # not the location: it plays
    return sorted(out)


def text_nodes(root):
    coll = bpy.data.collections.get(root)
    ids = (re.match(r"line\d+", ob.get("llb_node", "")) for ob in (coll.all_objects if coll else ()))
    return sorted({m.group(0) for m in ids if m})          # line003_g…, line003_fxo (an exit's plane): line003


def visible(win, area, name):
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region):
        lc = bpy.context.view_layer.layer_collection.children.get(name)
        return lc.visible_get() if lc else None


def settle(extra=0.3, limit=40.0):
    """Wait until the scheduled trial rebuild has run (it takes a few seconds on a busy machine)."""
    waited = 0.0
    while bpy.app.timers.is_registered(trial._rebuild) and waited < limit:
        yield 0.2
        waited += 0.2
    yield extra


def view3d(win):
    return [a for a in win.screen.areas if a.type == "VIEW_3D"]


def steps():
    main = bpy.context.scene
    proj = main.llb
    wm = bpy.context.window_manager
    win0 = wm.windows[0]
    text = bpy.data.texts.new("LLB_Lyrics")
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        text.from_string(f.read())
    proj.lyrics_text = text
    proj.font_body.filepath = font_arg()
    with bpy.context.temp_override(window=win0):
        bpy.ops.llb.refresh()
        bpy.ops.llb.omakase()
    main_before = sig("LyricLive")
    check(len(main_before) > 50 and proj.trial_snapshot, "the main preview is generated and saved as Before")
    n_areas = len(win0.screen.areas)
    main.use_audio, main.use_preview_range = True, False             # use_audio: True = the song plays

    def open_trial():
        area = view3d(win0)[0]
        region = next(r for r in area.regions if r.type == "WINDOW")
        with bpy.context.temp_override(window=win0, area=area, region=region):
            return bpy.ops.llb.trial_open()

    proj.line_active = 3
    check(open_trial() == {"FINISHED"}, "Try Out opens")
    yield from settle()
    win, sides = trial.views()
    others = [a for a in view3d(win0) if a not in sides]
    check(win == win0 and len(sides) == 2 and len(others) == 1 and len(wm.windows) == 1,
          "two views beside the user's 3D view, in the same window")
    if len(sides) == 2:
        check(sides[0].x < sides[1].x < others[0].x,
              f"Before, After, then the user's view with the sidebar {[sides[0].x, sides[1].x, others[0].x]}")
        check(visible(win, sides[0], trial.BEFORE) and not visible(win, sides[0], trial.AFTER), "the left view shows Before")
        check(visible(win, sides[1], trial.AFTER) and not visible(win, sides[1], trial.BEFORE), "the next view shows After")
        check(not visible(win, others[0], trial.BEFORE) and not visible(win, others[0], trial.AFTER)
              and visible(win, others[0], "LyricLive"), "the user's view shows neither, but the main preview")
    check(bpy.data.collections[trial.AFTER].hide_render and bpy.data.collections[trial.BEFORE].hide_render,
          "the trial objects stay out of renders")
    check(text_nodes(trial.BEFORE) == text_nodes(trial.AFTER) == ["line003"],
          f"both show line 4 only ({text_nodes(trial.BEFORE)} / {text_nodes(trial.AFTER)})")
    check(sig(trial.BEFORE) == sig(trial.AFTER), "with nothing changed, Before and After are the same")
    check(win0.screen.is_animation_playing and main.use_preview_range
          and main.frame_preview_end > main.frame_preview_start, "it loops over the line")

    # a change rebuilds After only
    before = sig(trial.BEFORE)
    chosen = planning.make_plan(proj).lines[3]
    proj.lines[3].layout = next(k for k in ("front", "pillar") if k != chosen.layout)
    proj.lines[3].enter = next(k for k in ("fade", "zoom") if k != chosen.enter)
    yield from settle()
    check(sig(trial.AFTER) != before, "changing the layout rebuilds After")
    check(sig(trial.BEFORE) == before, "Before stays")
    check(sig("LyricLive") == main_before, "the main preview stays until Confirm")

    with bpy.context.temp_override(window=win0):
        bpy.ops.llb.trial_revert()
    yield from settle()
    check(proj.lines[3].layout == "AUTO" and proj.lines[3].enter == "AUTO", "Back to Before sets the line back")
    check(sig(trial.AFTER) == sig(trial.BEFORE), "...and After is Before again")

    proj.lines[3].layout = next(k for k in ("front", "pillar") if k != chosen.layout)
    yield from settle()
    after = sig(trial.AFTER)
    with bpy.context.temp_override(window=win0):
        bpy.ops.llb.trial_commit()
    yield from settle()
    check(sig("LyricLive") != main_before, "Confirm rebuilds the main preview")
    check(sig(trial.BEFORE) == after == sig(trial.AFTER), "...and Before becomes After")

    if len(sides) == 2:
        r3d = sides[0].spaces.active.region_3d
        r3d.view_distance = r3d.view_distance + 2.0
        yield 0.5
        check(abs(sides[1].spaces.active.region_3d.view_distance - r3d.view_distance) < 1e-4, "the views move together")

    proj.trial_mute = True
    check(not main.use_audio, "Mute silences the song")
    proj.trial_mute = False
    check(main.use_audio, "...and unmuting brings it back")

    proj.section_active = 1
    yield from settle()
    sec = proj.sections[1]
    t = (main.frame_preview_start - main.frame_start) / (main.render.fps / main.render.fps_base)
    check(text_nodes(trial.AFTER) == [] and abs(t - max(0.0, sec.start - 1.5)) < 0.1, "a picked section shows its start")

    proj.trial_mute = True
    with bpy.context.temp_override(window=win0):
        bpy.ops.llb.trial_close()
    yield 0.6
    check(len(win0.screen.areas) == n_areas and not trial.is_open(), "Close puts the layout back")
    check(bpy.data.collections.get(trial.AFTER) is None and bpy.data.collections.get(trial.BEFORE) is None,
          "...removes the trial objects")
    check(not main.use_preview_range and main.use_audio and trial.RESTORE not in main,
          "...and puts the range and the sound back")
    check(len(sig("LyricLive")) > 50, "the main preview is still there")

    # the user closes one of the views
    open_trial()
    yield from settle()
    win, sides = trial.views()
    with bpy.context.temp_override(window=win0, area=sides[1]):
        bpy.ops.screen.area_close()
    yield 0.6
    check(not trial.is_open() and bpy.data.collections.get(trial.AFTER) is None and not main.use_preview_range,
          "closing a view by hand cleans up too")
    win, sides = None, []
    for area in [a for a in view3d(win0)][:-1]:                     # the Before view left over
        with bpy.context.temp_override(window=win0, area=area):
            bpy.ops.screen.area_close()

    # line details beside the 3D view (spec §6.2)
    from mathutils import Vector
    from lyric_live_builder.ui import details, panels
    if win0.screen.is_animation_playing:
        with bpy.context.temp_override(window=win0):
            bpy.ops.screen.animation_cancel(restore_frame=False)
    proj.ui_page = "compose"
    n0 = len(win0.screen.areas)
    user = view3d(win0)[0]
    with bpy.context.temp_override(window=win0, area=user):
        check(bpy.ops.llb.line_details(index=5) == {"FINISHED"}, "Details opens")
    yield 2.0                                   # the new area is laid out, then aimed
    _, area = details.area()
    rest = [a for a in view3d(win0) if a != area]
    check(area is not None and len(win0.screen.areas) == n0 + 1 and proj.line_active == 5,
          "a details area is added and the line is picked")
    if area is not None and rest:
        check(area.x < rest[0].x and area.width < rest[0].width, f"narrow, on the left ({area.width} / {rest[0].width})")
        ctx = lambda a: type("Ctx", (), {"scene": main, "area": a})()
        check(details.LLB_PT_line_details.poll(ctx(area)) and not panels.LLB_PT_lines.poll(ctx(area))
              and not panels.LLB_PT_pages.poll(ctx(area)), "the details area shows the line details only")
        ui = next(r for r in area.regions if r.type == "UI")
        check(area.spaces.active.show_region_ui and ui.active_panel_category == "LyricLive",
              f"its sidebar opens on the LyricLive tab ({ui.active_panel_category})")
        check(not details.LLB_PT_line_details.poll(ctx(rest[0])) and panels.LLB_PT_lines.poll(ctx(rest[0]))
              and panels.LLB_PT_sections.poll(ctx(rest[0])), "the main sidebar keeps sections and lines, no details")

        def looks_at_line():
            from bpy_extras.view3d_utils import location_3d_to_region_2d
            d, dist, t = details.target(proj)
            r3d = area.spaces.active.region_3d
            fwd = r3d.view_rotation @ Vector((0.0, 0.0, -1.0))
            eye = r3d.view_location - fwd * r3d.view_distance
            region = next(r for r in area.regions if r.type == "WINDOW")
            seen = region.width - (ui.width if region.width >= area.width - 2 else 0)        # left of the sidebar
            p = location_3d_to_region_2d(region, r3d, eye + d * dist)
            now = (main.frame_current - main.frame_start) / (main.render.fps / main.render.fps_base)
            return ((eye - Vector((0.0, 0.0, 1.5))).length < 1e-3 and p is not None and abs(p.x - seen / 2) < 0.1 * seen
                    and 0 <= p.y <= region.height and abs(now - t) < 0.05), p, seen
        ok, p, seen = looks_at_line()
        check(ok, f"its view looks at the line from the eye, beside the sidebar, at the line's time ({p} / {seen})")
        proj.line_active = 9
        yield 1.0
        ok, p, seen = looks_at_line()
        check(ok, f"picking another line turns the view to it ({p} / {seen})")
    with bpy.context.temp_override(window=win0):
        bpy.ops.llb.line_details_close()
    yield 0.4
    check(len(win0.screen.areas) == n0 and not details.is_open(), "Close removes the details area")

    # a file saved with the trial open
    open_trial()
    yield from settle()
    trial._after_load()
    check(bpy.data.collections.get(trial.AFTER) is None and trial.RESTORE not in main and not main.use_preview_range,
          "a file loaded with the trial left open is put back")
    llb.unregister()
    finish()


def run():
    try:
        delay = next(GEN)
    except StopIteration:
        return None
    except Exception:
        log.append(traceback.format_exc())
        failures.append("exception")
        finish()
        return None
    return delay


llb.register()
GEN = steps()
bpy.app.timers.register(run, first_interval=1.0)
