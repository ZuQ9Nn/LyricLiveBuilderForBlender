"""Thumbnails of every layout and motion part (design §13), drawn by the add-on's own preview.

  blender --background --factory-startup --python tools/make_part_thumbnails.py [-- --font <file>]

Writes lyric_live_builder/thumbnails/<kind>.png (a row per part, a column per frame) and index.json, for the
layouts, the motions, the particle presets, the backgrounds and the styles. LLB_THUMB_KINDS=particle,style makes
only those (the other rows of index.json stay). Run it again after adding or changing parts
(tests/core/test_thumbnails.py checks that every one has its row).
The letters are drawn with BIZ UDGothic / BIZ UDMincho (SIL Open Font License) when they are installed."""
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
from lyric_live_builder.core import atlas, bake, model, registry, styles, world, xform    # noqa: E402
from lyric_live_builder.core.parts import backgrounds as bgs         # noqa: E402
from lyric_live_builder.core.parts import particles as pts           # noqa: E402
from lyric_live_builder.preview import scene as preview_scene        # noqa: E402
from lyric_live_builder.ui import planning, project                  # noqa: E402

OUT = os.path.join(ROOT, "lyric_live_builder", "thumbnails")
TILE = 96
FRAMES = {"layout": 1, "enter": 8, "hold": 8, "exit": 8, "particle": 8, "background": 1, "style": 1}
KINDS = tuple(FRAMES)
PARTICLE_SPAN = 2.0                              # seconds of a particle preset shown
GRAIN = 0.1                                      # radians: grains are made at least this big as seen (~6 px)
MAX_GROW = 5.0                                   # ...but grown at most this much (most are under a pixel)
SKY_PITCH = 40.0                                 # degrees up for the presets on the sky shell
SERIF = r"C:\Windows\Fonts\BIZ-UDMinchoM.ttc"     # the serif styles' letters (else the body font)
HOLD_SPAN = 3.2                                  # seconds of a hold motion shown (most repeat in 2.4-3.2 s)
PROBE = 16                                       # trial shots to find when an entrance has settled
SETTLED = 0.002                                  # mean difference (0..1) below which two shots are the same
FOV = {"layout": 95.0, "motion": 56.0, "particle": 90.0, "background": 100.0}   # degrees (a 4-letter line: ~48)
MOTION_LINE, LAYOUT_LINE = 0, 1                  # "あいうえ", "あいうえおかきく"
THUMB_ANGLE = 12.0                               # letters at this visual angle, whole lines: the thumbnails show a
                                                 # part's shape, framed by FOV, whatever the text size setting
TMP = os.path.join(bpy.app.tempdir, "llb_thumb.png")


def stage():
    llb.register()
    model.TEXT_SCALE = THUMB_ANGLE / model.TEXT_ANGLE["mid"]
    for ob in list(bpy.data.objects):                    # the start-up cube, light and camera stay out
        bpy.data.objects.remove(ob)
    scene, proj = setup("あいうえ\nあいうえおかきく\nおわり\n", font_arg())
    for ln, t in zip(proj.lines, (1.0, 8.0, 15.0)):
        ln.tap_time = t
        ln.guide, ln.gimmick, ln.persist, ln.cuts = "off", "none", "next", "1"
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
    cam.rotation_euler = (math.radians(90), 0.0, 0.0)
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


def keys_of(kind):
    """The rows of a kind: what the panels can show (a panorama needs the user's image: none)."""
    if kind == "particle":
        return list(pts.PRESETS)
    if kind == "background":
        return [k for k in bgs.ORDER if not bgs.needs_image(k)]
    if kind == "style":
        return list(styles.ORDER)
    return registry.keys(kind)


def stage_frames(scene, proj, cam, kind, key):
    """A particle preset (frames) or a background (one) from the eye, without the letters."""
    for ln in proj.lines:
        ln.layout, ln.enter, ln.hold, ln.exit = "front", "fade", "still", "fade"
        ln.is_3d = False
    for sec in proj.sections:
        sec.background = key if kind == "background" else "AUTO"
    plan = planning.make_plan(proj)
    plan.gimmicks, plan.events = [], []
    t0 = plan.section_plans[0].start + 0.5
    if kind == "particle":                               # that preset alone, in front of the eye
        front = [float(x) for x in pts.EYE + model.DISTANCE["mid"] * xform.direction(0.0, 0.0)]
        bursts = [{"t": t0 + 0.3, "origin": front}, {"t": t0 + 1.3, "origin": front}] \
            if pts.PRESETS[key]["emitter"] == "burst" else None
        proj.fx.particles = 1.0                          # as many as the UI allows
        spec = world.emitter(key, t0, t0 + 8.0, 7, plan.section_plans[0].palette, planning.settings(proj),
                             bursts=bursts)
        p = spec["preset"]
        r = sum(p.get("radius", (model.DISTANCE["mid"],) * 2)) / 2
        dist = math.hypot(r, sum(p["height"]) / 2) if "height" in p else r
        grow = min(MAX_GROW, max(1.0, GRAIN * dist / max(p["size"])))
        p["size"] = tuple(v * grow for v in p["size"])
        plan.emitters = [spec]
    else:
        plan.emitters = []
    baked = bake.bake(plan, project.metrics(proj))
    preview_scene.build(scene, baked, lambda role: project.font_paths(proj, role))
    show = preview_scene.CATEGORY_COLLECTIONS["particles" if kind == "particle" else "background"]
    for coll in bpy.data.collections[preview_scene.ROOT].children:
        coll.hide_render = coll.name != show
    scene.camera = cam
    cam.data.angle = math.radians(FOV[kind])
    up = SKY_PITCH if kind == "particle" and pts.PRESETS[key]["emitter"] == "sky_shell" else 0.0
    cam.rotation_euler = (math.radians(90 + up), 0.0, 0.0)
    if kind == "background":
        return np.stack([shoot(scene, t0 + 1.0)])
    if bursts:
        a = t0 + 0.2                                     # from the first burst
    else:                                                # a flow once it is going, where most is seen (rare ones)
        probe = [t0 + 1.0 + k for k in range(6)]
        a = max(probe, key=lambda t: float(np.abs(np.diff(shoot(scene, t)[..., :3], axis=0)).mean()))
    return np.stack([shoot(scene, a + PARTICLE_SPAN * k / FRAMES[kind]) for k in range(FRAMES[kind])])


def _hex(c):
    return np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)], dtype=np.float32) / 255.0


def text_mask(path):
    """Coverage (TILE, TILE) of "歌詞" in a font, white on black, from an orthographic camera."""
    sc = bpy.data.scenes.new("LLB_Mask")
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = TILE
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("LLB_Mask")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
    cu = bpy.data.curves.new("LLB_Mask", "FONT")
    cu.body, cu.size, cu.align_x, cu.align_y = "歌詞", 0.36, "CENTER", "CENTER"
    cu.font = bpy.data.fonts.load(path, check_existing=True)
    mat = bpy.data.materials.new("LLB_Mask")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    em, out = nodes.new("ShaderNodeEmission"), nodes.new("ShaderNodeOutputMaterial")
    em.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    mat.node_tree.links.new(em.outputs[0], out.inputs[0])
    cu.materials.append(mat)
    ob = bpy.data.objects.new("LLB_Mask", cu)
    ob.location.y = 0.04                                 # a little above the middle: the accent bar goes below
    cam = bpy.data.objects.new("LLB_MaskCam", bpy.data.cameras.new("LLB_MaskCam"))
    cam.data.type, cam.data.ortho_scale = "ORTHO", 1.0
    cam.location.z = 2.0
    for o in (ob, cam):
        sc.collection.objects.link(o)
    sc.camera = cam
    sc.render.filepath = TMP
    bpy.ops.render.render(write_still=True, scene=sc.name)
    img = bpy.data.images.load(TMP)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(TILE, TILE, 4)[::-1, :, 0]
    bpy.data.images.remove(img)
    bpy.data.scenes.remove(sc)
    return px


def style_tile(key, masks):
    """Like JIZURA's style tiles: the first scheme's background, the letters with their two ghosts, the accent bar
    and the other schemes' backgrounds as swatches."""
    st = styles.STYLES[key]
    sc = st["schemes"][0]
    m = masks["serif" if st.get("body") == "serif" else "body"]
    img = np.empty((TILE, TILE, 3), dtype=np.float32)
    img[:] = _hex(sc["bg"])
    for col, (dy, dx) in ((sc["ghostB"], (-1, -2)), (sc["ghostA"], (1, 2)), (sc["fg"], (0, 0))):
        a = np.roll(m, (dy, dx), axis=(0, 1))[..., None]
        img = img * (1 - a) + _hex(col) * a
    img[TILE - 22:TILE - 18, 12:34] = _hex(sc["accent"])
    for i, other in enumerate(st["schemes"][1:4]):
        img[0:8, TILE - 12 * (i + 1):TILE - 12 * i] = _hex(other["bg"])
    return np.concatenate([img, np.ones((TILE, TILE, 1), np.float32)], axis=2)[None]


def main():
    os.makedirs(OUT, exist_ok=True)
    scene, proj, cam = stage()
    kinds = [k for k in os.environ.get("LLB_THUMB_KINDS", ",".join(KINDS)).split(",") if k]
    path = os.path.join(OUT, "index.json")
    index = {"tile": TILE, "frames": dict(FRAMES), "rows": {}}
    if os.path.isfile(path) and set(kinds) != set(KINDS):                # the other kinds stay
        with open(path, encoding="utf-8") as f:
            index["rows"] = {k: v for k, v in json.load(f)["rows"].items() if k in KINDS}
    masks = {}
    if "style" in kinds:
        font = font_arg()
        masks = {"body": text_mask(font), "serif": text_mask(SERIF if os.path.isfile(SERIF) else font)}
    t0, failed = time.time(), []
    for kind in kinds:
        keys = keys_of(kind)[:int(os.environ.get("LLB_THUMB_LIMIT", "0")) or None]     # a quick trial
        sheet = np.zeros((len(keys) * TILE, FRAMES[kind] * TILE, 4), dtype=np.float32)
        for row, key in enumerate(keys):
            try:
                tiles = style_tile(key, masks) if kind == "style" else \
                    stage_frames(scene, proj, cam, kind, key) if kind in ("particle", "background") else \
                    frames(scene, proj, cam, kind, key)
            except Exception as e:                                       # keep going: a blank tile
                failed.append(f"{kind}:{key}: {e}")
                continue
            for k, tile in enumerate(tiles):
                sheet[row * TILE:(row + 1) * TILE, k * TILE:(k + 1) * TILE] = tile
            print(f"[{time.time() - t0:6.1f}s] {kind} {key}", flush=True)
        with open(os.path.join(OUT, f"{kind}.png"), "wb") as f:
            f.write(atlas.png_bytes(sheet))
        index["rows"][kind] = keys
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print("FAILED", failed)
    print("DONE", round(time.time() - t0, 1))


main()
