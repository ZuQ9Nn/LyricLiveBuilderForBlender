"""Thumbnails of every layout and motion part (design §13), drawn by the add-on's own preview.

  blender --background --factory-startup --python tools/make_part_thumbnails.py [-- --font <file>]

Writes lyric_live_builder/thumbnails/<kind>.png (a row per part, a column per frame) and index.json.
Run it again after adding or changing parts (tests/core/test_thumbnails.py checks that every part has one).
The letters are drawn with BIZ UDGothic (SIL Open Font License) when it is installed."""
import json
import math
import os
import sys
import time

import bpy
import numpy as np

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests", "blender")]

import lyric_live_builder as llb                                     # noqa: E402
from common import font_arg, setup                                   # noqa: E402
from lyric_live_builder.core import atlas, bake, registry           # noqa: E402
from lyric_live_builder.preview import scene as preview_scene        # noqa: E402
from lyric_live_builder.ui import planning, project                  # noqa: E402

OUT = os.path.join(ROOT, "lyric_live_builder", "thumbnails")
TILE = 96
FRAMES = {"layout": 1, "enter": 8, "hold": 8, "exit": 8}
HOLD_SPAN = 3.2                                  # seconds of a hold motion shown (most repeat in 2.4-3.2 s)
PROBE = 16                                       # trial shots to find when an entrance has settled
SETTLED = 0.002                                  # mean difference (0..1) below which two shots are the same
FOV = {"layout": 95.0, "motion": 56.0}           # degrees: a 4-letter line spans about 48 deg; layouts spread wide
MOTION_LINE, LAYOUT_LINE = 0, 1                  # "あいうえ", "あいうえおかきく"
TMP = os.path.join(bpy.app.tempdir, "llb_thumb.png")


def stage():
    llb.register()
    for ob in list(bpy.data.objects):                    # the start-up cube, light and camera stay out
        bpy.data.objects.remove(ob)
    scene, proj = setup("あいうえ\nあいうえおかきく\nおわり\n", font_arg())
    for ln, t in zip(proj.lines, (1.0, 8.0, 15.0)):
        ln.tap_time = t
        ln.guide, ln.gimmick, ln.distance_layer, ln.persist = "off", "none", "mid", "next"
    proj.fx.spectrum = "off"
    project.recompute(scene)
    cam = bpy.data.objects.new("LLB_Thumb", bpy.data.cameras.new("LLB_Thumb"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0.0, 0.0, 1.5)
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)          # from the eye, straight ahead
    r = scene.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x = r.resolution_y = TILE
    r.resolution_percentage = 100
    r.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    scene.world = scene.world or bpy.data.worlds.new("LLB_Thumb")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.03, 0.03, 0.05, 1.0)
    return scene, proj, cam


def shoot(scene, t):
    fps = scene.render.fps / scene.render.fps_base
    f = t * fps
    scene.frame_set(scene.frame_start + int(f), subframe=f % 1.0)
    scene.render.filepath = TMP
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(TMP)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(TILE, TILE, 4)[::-1]      # bottom-up -> top-down
    bpy.data.images.remove(img)
    return px


def frames(scene, proj, cam, kind, key):
    """The part's frames (n, TILE, TILE, 4)."""
    target = LAYOUT_LINE if kind == "layout" else MOTION_LINE
    for i, ln in enumerate(proj.lines):
        ln.layout, ln.enter, ln.hold, ln.exit = "front", "fade", "still", "fade"
        ln.is_3d = False
    ln = proj.lines[target]
    setattr(ln, kind, key)
    proj.fx.motion = 1.0 if kind == "hold" else 0.7      # holds are subtle: at the strongest the UI allows
    if kind == "layout" and getattr(registry.get("layout", key), "only_3d", False):
        ln.is_3d = True
    plan = planning.make_plan(proj)
    plan.world, plan.emitters, plan.gimmicks, plan.events = [], [], [], []       # the letters only
    lp = plan.lines[target]
    baked = bake.bake(plan, project.metrics(proj))
    preview_scene.build(scene, baked, lambda role: project.font_paths(proj, role))
    for coll in bpy.data.collections[preview_scene.ROOT].children:
        coll.hide_render = coll.name != preview_scene.TEXT
    scene.camera = cam                                   # the preview makes its audience camera the scene's
    cam.data.angle = math.radians(FOV["layout" if kind == "layout" else "motion"])
    n = FRAMES[kind]
    if kind == "layout":
        times = [lp.start + lp.enter_dur + 0.4]
    elif kind == "enter":                                # until the letters stop moving
        span = max(lp.enter_dur, lp.char_times[-1] - lp.start + lp.enter_dur)     # letters may come as sung
        probe = [lp.start + span * k / (PROBE - 1) for k in range(PROBE)]
        shots = [shoot(scene, t) for t in probe]
        moving = [k for k in range(PROBE) if np.abs(shots[k] - shots[-1]).mean() > SETTLED]
        end = probe[min(max(moving, default=0) + 1, PROBE - 1)]
        times = [lp.start + (end - lp.start) * k / (n - 1) for k in range(n)]
    elif kind == "hold":
        a = lp.start + lp.enter_dur + 0.1
        span = min(HOLD_SPAN, lp.end - lp.exit_dur - 0.05 - a)              # a 4-letter line shows ~3.6 s
        times = [a + span * k / n for k in range(n)]                         # loops without a doubled frame
    else:
        times = [lp.end - lp.exit_dur + lp.exit_dur * k / (n - 1) for k in range(n)]
    return np.stack([shoot(scene, t) for t in times])


def main():
    os.makedirs(OUT, exist_ok=True)
    scene, proj, cam = stage()
    index = {"tile": TILE, "frames": FRAMES, "rows": {}}
    t0, failed = time.time(), []
    for kind in ("layout", "enter", "hold", "exit"):
        keys = registry.keys(kind)[:int(os.environ.get("LLB_THUMB_LIMIT", "0")) or None]     # a quick trial
        sheet = np.zeros((len(keys) * TILE, FRAMES[kind] * TILE, 4), dtype=np.float32)
        for row, key in enumerate(keys):
            try:
                tiles = frames(scene, proj, cam, kind, key)
            except Exception as e:                                       # keep going: a blank tile
                failed.append(f"{kind}:{key}: {e}")
                continue
            for k, tile in enumerate(tiles):
                sheet[row * TILE:(row + 1) * TILE, k * TILE:(k + 1) * TILE] = tile
            print(f"[{time.time() - t0:6.1f}s] {kind} {key}", flush=True)
        with open(os.path.join(OUT, f"{kind}.png"), "wb") as f:
            f.write(atlas.png_bytes(sheet))
        index["rows"][kind] = keys
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print("FAILED", failed)
    print("DONE", round(time.time() - t0, 1))


main()
