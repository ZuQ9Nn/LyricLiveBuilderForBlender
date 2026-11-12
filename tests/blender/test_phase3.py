"""Phase 3 integration test (background Blender, no MCP).

  blender --background --factory-startup --python tests/blender/test_phase3.py [-- --font <ttf/otf/ttc>]

おまかせ, proposal history, locks, "change only this", the dome (checked in an EEVEE render),
the particle preview against core, gaze guides and the speed of a four minute song.
"""
import json
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
from common import check, failures, font_arg, setup, song, text_objects, translation_checks  # noqa: E402
from lyric_live_builder.core import bake, color, world               # noqa: E402
from lyric_live_builder.core.parts import backgrounds as bgs          # noqa: E402
from lyric_live_builder.core.parts import lines, particles as pts     # noqa: E402
from lyric_live_builder.preview import particles as preview_particles  # noqa: E402
from lyric_live_builder.preview import scene as preview_scene        # noqa: E402
from lyric_live_builder.ui import planning, project                  # noqa: E402


def frame_set(scene, t):
    f = scene.frame_start + t * scene.render.fps / scene.render.fps_base
    scene.frame_set(int(math.floor(f)), subframe=f - math.floor(f))


def composition(plan):
    return [(x.layout, x.enter, x.hold, x.exit, x.distance) for x in plan.lines]


def render_center(scene, t, path):
    """sRGB colour at the middle of a tiny render of the dome alone. Rendered until two results agree:
    Blender 5.0 renders in the background before the dome shader has compiled (black at first)."""
    frame_set(scene, t)
    scene.render.filepath = path
    last = None
    for _ in range(8):
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(path)
        w, h = img.size
        c = np.array(img.pixels[:]).reshape(h, w, 4)[h // 2, w // 2, :3]   # odd size: exactly at the horizon
        bpy.data.images.remove(img)
        if last is not None and np.abs(c - last).max() < 1e-3:
            break
        last = c
    return c


def check_dome(scene, plan):
    root = bpy.data.collections[preview_scene.ROOT]
    for c in root.children:
        c.hide_render = c.name not in (preview_scene.CAMERA, "LLB_Background")
    for ob in bpy.data.collections["LLB_Background"].objects:
        if ob.get("llb_node", "").startswith("far"):
            ob.hide_render = True                       # keep the view on the dome itself
            if ob.animation_data:
                ob.animation_data.action = None
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 33, 19, 100
    scene.view_settings.view_transform = "Standard"
    scene.render.filter_size = 0.0                      # no pixel filter: the steep horizon gradient would blur in
    scene.render.image_settings.file_format = "PNG"
    calm = [w for w in plan.world]
    flashes = [e["t"] for e in plan.events if e["type"] == "flash"]
    worst, n = 0.0, 0
    for w0, w1 in zip(calm, calm[1:] + [None]):
        t = (w0["t"] + w0["dur"] + (w1["t"] if w1 else plan.duration)) / 2
        if any(abs(t - f) < 1.0 for f in flashes):
            t += 1.2
        spec = world.active_background(plan.world, t)
        if spec["mode"] in (bgs.MODE["image"], bgs.MODE["pattern"]):
            continue                                    # a pattern line may cross the horizon pixel
        got = render_center(scene, t, os.path.join(bpy.app.tempdir, f"llb_dome_{n}.png"))
        want = np.array(color.rgb(spec["horizon"])) / 255
        worst = max(worst, float(np.abs(got - want).max()))
        print(f"     dome t={t:.1f} {spec['key']} got {np.round(got, 3)} want {np.round(want, 3)}")
        n += 1
    for c in root.children:
        c.hide_render = False
    return worst, n


def check_particles(scene, baked, t):
    """Quad centres of every live particle == core.parts.particles.state()."""
    frame_set(scene, t)
    preview_particles.update_scene(scene)
    worst, alive = 0.0, 0
    specs = {e["node"]: e["spec"] for e in baked.emitters}
    for ob in bpy.data.collections["LLB_Particles"].objects:
        spec = specs[ob["llb_node"]]
        st = pts.state(spec, (scene.frame_current - scene.frame_start + scene.frame_subframe) / scene.render.fps)
        cap = spec["count"] + spec["pool"]
        co = np.empty(len(ob.data.vertices) * 3, dtype=np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        if spec["preset"]["shape"] in pts.SHAPES_3D and not lines.is_lines(spec["preset"]):
            centres, base = np.zeros((cap, 3)), 0                # grouped by shape (mixed shapes differ in size)
            for slots, v, _ in preview_particles._layout3d(spec["preset"], spec["seed"], cap):
                n = len(v) * len(slots)
                centres[slots] = co[base:base + n].reshape(len(slots), len(v), 3).mean(axis=1)
                base += n
        else:
            centres = co.reshape(-1, 4, 3).mean(axis=1)[:cap]     # heads (tails follow)
        live = st["alpha"] > 0
        if spec["preset"].get("trail") or not live.any():
            alive += int(live.sum())
            continue
        if spec["preset"]["shape"] in pts.SHAPES_3D:
            from lyric_live_builder.core import meshes
            offset = max(np.linalg.norm(meshes.particle_shape(k)[0].mean(axis=0)) for k in pts.shapes_of(spec["preset"]))
            tol = offset * st["size"][live].max() + 1e-3      # shapes are about centred; rotation moves the mean a little
        else:
            tol = 1e-3
        err = np.linalg.norm(centres[live] - st["pos"][live], axis=1).max()
        worst = max(worst, float(err - tol + 1e-3))
        alive += int(live.sum())
    return worst, alive


def main():
    font = font_arg()
    llb.register()
    from lyric_live_builder.core.rng import Rng
    rolls = iter(range(1000, 2000))
    planning.random = lambda: Rng(next(rolls))         # fixed proposals: the test does the same every run
    with open(os.path.join(ROOT, "tests", "manual", "lyrics_sample.txt"), encoding="utf-8") as f:
        sample = f.read()
    scene, proj = setup(sample, font)
    scene.render.fps = 30
    path = os.path.join(bpy.app.tempdir, "llb_phase3_song.wav")
    song(path)
    bpy.ops.llb.load_audio(filepath=path)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 4.0 + i * 4.0 + (8.0 if i >= 8 else 0.0)
    project.recompute(scene)
    check(len(proj.parts) > 60, f"part switches listed ({len(proj.parts)})")

    # おまかせ builds everything at once
    r = bpy.ops.llb.omakase()
    check(r == {"FINISHED"}, "make it for me")
    check(len(proj.history) == 2 and proj.history_index == 1, "the first proposal and the one before it are kept")
    plan1 = planning.make_plan(proj)
    baked1 = bake.bake(plan1, project.metrics(proj))
    colls = {c.name: len(c.objects) for c in bpy.data.collections[preview_scene.ROOT].children}
    check(colls.get(preview_scene.TEXT, 0) > 100, f"text built {colls}")
    check(any(ob.get("llb_node") == "dome" for ob in bpy.data.collections["LLB_Background"].objects), "dome built")
    check(colls.get("LLB_Particles", 0) == len(baked1.emitters) > 0, f"one object per particle emitter ({len(baked1.emitters)})")
    check(colls.get("LLB_Guide", 0) == sum(1 + g["motes"] + ("glow" in g["kinds"]) for g in baked1.guides),
          f"guide objects ({len(baked1.guides)} guides, each a pivot with motes and glow)")
    check(len({w["spec"]["key"] for w in plan1.world}) >= 2, "the background changes over the song")

    # particle preview == core
    sp = plan1.section_plans[len(plan1.section_plans) // 2]
    worst, alive = check_particles(scene, baked1, (sp.start + sp.end) / 2 + 0.013)
    check(alive > 20 and worst < 2e-3, f"particle preview matches core ({alive} alive, worst {worst * 1000:.2f} mm)")
    t0 = time.perf_counter()
    for k in range(30):
        frame_set(scene, 5.0 + k * 0.5)
        preview_particles.update_scene(scene)
    per_frame = (time.perf_counter() - t0) / 30
    check(per_frame < 0.1, f"particle update per frame {per_frame * 1000:.0f} ms")

    # history: another proposal, then back
    bpy.ops.llb.omakase()
    plan2 = planning.make_plan(proj)
    check(planning.history_state(proj, 2) != planning.history_state(proj, 1), "another proposal")
    bpy.ops.llb.history_step(step=-1)
    back = planning.make_plan(proj)
    check(proj.history_index == 1 and composition(back) == composition(plan1) and
          [w["spec"]["key"] for w in back.world] == [w["spec"]["key"] for w in plan1.world],
          "Previous Proposal brings the first proposal back")
    bpy.ops.llb.history_step(step=1)
    check(composition(planning.make_plan(proj)) == composition(plan2), "Next Proposal goes forward again")

    # a locked line keeps its composition through おまかせ
    proj.line_active = 3
    bpy.ops.llb.line_lock()
    before = planning.make_plan(proj)
    for _ in range(3):
        bpy.ops.llb.omakase()
    after = planning.make_plan(proj)
    check(composition(after)[3] == composition(before)[3], "the locked line stays as it was")
    check(composition(after) != composition(before), "the other lines change")
    bpy.ops.llb.line_lock()                                     # unlock
    check(not proj.lines[3].locked and proj.lines[3].layout == "AUTO", "unlocking returns the line to automatic")

    # a line in cuts: shown in turn, and locked cut by cut
    def cuts():
        return [(c.text, c.layout, c.enter, c.hold, c.exit, c.distance) for c in planning.make_plan(proj).lines[3].cuts]

    proj.lines[3].cuts = "3"
    bpy.ops.llb.preview_build()
    check(len(cuts()) == 3 and all(any(o.name.startswith(f"LLB_L004{x}_") for o in bpy.data.objects) for x in ("", "-2", "-3")),
          "a line in 3 cuts is previewed as 3 groups")
    before = cuts()
    bpy.ops.llb.line_lock()
    for _ in range(3):
        bpy.ops.llb.omakase()
    check(cuts() == before, "a locked line keeps each cut")
    bpy.ops.llb.line_lock()
    check(not proj.lines[3].lock_cuts and proj.lines[3].cuts == "3", "unlocking forgets the cuts' parts, not their number")
    proj.lines[3].cuts = "AUTO"
    check(planning.make_plan(proj).lines[3].cuts is None, "Planner's Choice shows the line whole")
    first = planning.make_plan(proj).lines[0]                    # "夜明けの色を/覚えてる" on Planner's Choice
    check([c.text for c in first.cuts or ()] == ["夜明けの色を", "覚えてる"], "a '/' in the lyrics makes a cut there")
    proj.lines[0].cuts = "1"
    check(planning.make_plan(proj).lines[0].cuts is None, "...unless the line is set to 1 cut")
    proj.lines[0].cuts = "AUTO"

    # copy / paste a line's effects (spec §6.2): lines 5 and 7 are both "光の粒を/集めて"
    def look(lp):
        return (lp.layout, lp.layout_params, lp.enter, lp.hold, lp.exit, lp.distance, lp.seed,
                [(c.text, c.layout, c.layout_params, c.enter, c.hold, c.exit, c.distance, c.seed) for c in lp.cuts or ()])
    proj.line_active = 4
    check(bpy.ops.llb.line_copy() == {"FINISHED"} and json.loads(proj.line_clipboard)["line"] == 4, "Copy Effects")
    proj.line_active = 6
    check(bpy.ops.llb.line_paste() == {"FINISHED"}, "Paste Effects")
    plan = planning.make_plan(proj)
    pasted = look(plan.lines[6])
    check(pasted == look(plan.lines[4]), "the pasted line looks as the copied one (Planner's Choice items included)")
    proj.lines[4].seed_offset += 1
    bpy.ops.llb.omakase()
    check(look(planning.make_plan(proj).lines[6]) == pasted, "...and stays when the source changes and on Make It for Me")
    bpy.ops.llb.line_lock()
    check(not bpy.ops.llb.line_paste.poll(), "no paste on a locked line")
    bpy.ops.llb.line_lock()

    # a locked section keeps its theme and background
    proj.section_active = 2
    bpy.ops.llb.section_lock()
    sec_before = planning.make_plan(proj).section_plans[2]
    bpy.ops.llb.omakase()
    sec_after = planning.make_plan(proj).section_plans[2]
    check((sec_before.theme, sec_before.background["key"]) == (sec_after.theme, sec_after.background["key"]),
          "the locked section keeps its theme and background")

    # the section panel shows what is really used (theme and background, spec §5)
    plan = planning.make_plan(proj)
    summary = planning.section_summary(proj)
    check([(s["theme"], s["background"], s["particles"]) for s in summary]
          == [(sp.theme, sp.background["key"], sp.particles) for sp in plan.section_plans],
          "the section panel shows the planned theme, background and particles")
    check(planning.section_summary(proj) is summary, "the panel summary is reused while nothing changes")
    proj.sections[1].background = "evening"
    summary = planning.section_summary(proj)
    check(summary[1]["background"] == "evening" and summary[1]["background_from"] == "section",
          "a section's own background is shown as set there")
    proj.sections[1].background = "AUTO"

    # change only the particles
    a = planning.make_plan(proj)
    proj.reroll_target = "particles"
    bpy.ops.llb.reroll()
    b = planning.make_plan(proj)
    check(composition(a) == composition(b) and [w["spec"]["key"] for w in a.world] == [w["spec"]["key"] for w in b.world],
          "changing the particles leaves text and backgrounds")
    check([(e["key"], e["seed"]) for e in a.emitters] != [(e["key"], e["seed"]) for e in b.emitters], "the particles change")
    ga = bake.bake(a, project.metrics(proj)).guides
    gb = bake.bake(b, project.metrics(proj)).guides
    check([(g["line"], g["t_hit"]) for g in ga] == [(g["line"], g["t_hit"]) for g in gb], "gaze guides stay")

    # a line changes the background with a ring
    ln = proj.lines[5]
    ln.background, ln.transition = "underwater", "ring"
    bpy.ops.llb.preview_build()
    plan = planning.make_plan(proj)
    w = next((x for x in plan.world if x["spec"]["key"] == "underwater" and abs(x["t"] - ln.start) < 1e-4), None)
    check(w is not None and w["transition"] == "ring", "line background override starts at the line with a ring")
    nodes = bpy.data.materials["LLB_Dome"].node_tree.nodes
    frame_set(scene, ln.start + 0.5)
    kind, prog = nodes["llb_trans"].outputs[0].default_value, nodes["llb_progress"].outputs[0].default_value
    check(abs(kind - 4.0) < 1e-6 and 0.0 < prog < 1.0, f"dome runs the ring (type {kind}, progress {prog:.2f})")
    ln.background = ln.transition = "AUTO"

    # strength slider: more particles
    proj.fx.particles = 0.1
    low = sum(e["count"] + e["pool"] for e in planning.make_plan(proj).emitters)
    proj.fx.particles = 0.95
    high = sum(e["count"] + e["pool"] for e in planning.make_plan(proj).emitters)
    check(high > low * 1.8, f"particle amount follows the slider ({low} -> {high})")

    # flashes: never more than 3 a second
    plan = planning.make_plan(proj)
    strong = sorted([e["t"] for e in plan.events if e["type"] == "flash" and e["amp"] >= world.STRONG] +
                    [x["t"] + x["dur"] / 2 for x in plan.world if bgs.TRANSITIONS.get(x["transition"], {}).get("flash")])
    check(all(b_ - a_ >= world.FLASH_GAP - 1e-9 for a_, b_ in zip(strong, strong[1:])), "strong flashes ≥ 0.4 s apart")

    # the dome shows the right background (EEVEE render, centre pixel = horizon colour)
    bpy.ops.llb.preview_build()
    worst, n = check_dome(scene, planning.make_plan(proj))
    check(n >= 2 and worst < 0.03, f"dome colour in a render matches the background ({n} checks, worst {worst:.3f})")

    # a four minute song
    long = "\n".join(["[A]"] + [f"{i}番目の歌詞の行をここに書く" for i in range(30)] + ["[サビ]"] +
                     [f"サビの{i}行目を高らかに歌う" for i in range(30)])
    scene, proj = setup(long, font)
    for i, ln in enumerate(proj.lines):
        ln.tap_time = 2.0 + i * 4.0
    project.recompute(scene)
    t0 = time.perf_counter()
    bpy.ops.llb.omakase()
    dt = time.perf_counter() - t0
    check(dt < 30.0, f"4 minute song made in {dt:.1f} s (< 30 s)")

    translation_checks()
    bpy.ops.llb.preview_clear()
    left = [ob for ob in bpy.data.collections[preview_scene.ROOT].all_objects if ob.type == "MESH"]
    check(not left, "delete")
    check(not [m for m in bpy.data.meshes if preview_particles.PROP in m], "particle meshes removed")
    llb.unregister()


try:
    main()
except Exception:
    traceback.print_exc()
    failures.append("exception")
print("RESULT", "PASS" if not failures else f"FAIL {failures}")
sys.exit(1 if failures else 0)
