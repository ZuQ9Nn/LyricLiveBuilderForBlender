"""Phase 3 core: colours, particles, atlas, backgrounds, world planning, guides, おまかせ (no Blender)."""
import math
import time
import unittest

import numpy as np

from lyric_live_builder.core import (atlas, audio, bake, bake_world, color, guide, meshes, model, moods, omakase,
                                     planner, styles, themes, world)
from lyric_live_builder.core.parts import backgrounds as bgs
from lyric_live_builder.core.parts import particles as pts
from lyric_live_builder.core.rng import Rng
from tests.core.test_text_parts import inputs, metrics, sections_for

EYE = np.array([0.0, 0.0, model.EYE_HEIGHT])
KINDS = ["intro", "verse", "chorus", "verse", "chorus", "outro"]


def make(n_lines=24, seed=7, settings=None, sec_len=16.0, **over):
    lines = inputs(n_lines, sec_len=sec_len, **over)
    duration = lines[-1].end + 2.0
    secs = [model.SectionInput(a, b, KINDS[k % len(KINDS)]) for k, (a, b) in enumerate(sections_for(duration, sec_len))]
    p = planner.plan(lines, secs, duration, seed, bpm=120, settings=settings)
    return p, bake.bake(p, metrics)


def visible_slot(baked, t):
    """Which dome slot the shader shows at t between transitions, from the tracks (crossfade mask)."""
    tr = {x.prop: x for x in baked.tracks if x.node == bake_world.DOME}

    def at(prop):
        x = tr[prop]
        if x.interp == "constant":
            return x.values[max(np.searchsorted(x.times, t, side="right") - 1, 0)]
        return np.array([np.interp(t, x.times, x.values[:, c]) for c in range(x.values.shape[1])])
    nxt, p = at("dome:next")[0], at("dome:progress")[0]
    q = p if nxt > 0.5 else 1 - p
    w_b = q if nxt > 0.5 else 1 - q
    return ("B" if w_b > 0.5 else "A"), at


class TestColour(unittest.TestCase):
    def test_contrast_fit(self):
        self.assertAlmostEqual(color.contrast("#FFFFFF", "#000000"), 21.0, places=3)
        for fg, bg in (("#222222", "#101018"), ("#EEEEEE", "#F0F0F0"), ("#FF0A8C", "#0B1030")):
            self.assertGreaterEqual(color.contrast(color.fit_contrast(fg, bg, 3.0), bg), 3.0 - 1e-9)

    def test_palettes_read_on_every_background(self):
        for st in styles.ORDER:
            for key in bgs.ORDER:
                spec = bgs.resolve(key, st)
                pal = styles.palette(st, bgs.backdrop(spec))
                self.assertGreaterEqual(color.contrast(pal["fg"], pal["bg"]), 3.0 - 1e-9, (st, key))
                self.assertGreaterEqual(color.contrast(pal["accent"], pal["bg"]), 2.4 - 1e-9, (st, key))


class TestParticles(unittest.TestCase):
    def spec(self, key, strength=0.6, start=2.0, end=14.0, intensity=None):
        sp = model.SectionPlan(0, "verse", start, end, "night_city", bgs.resolve("night"), [],
                               styles.palette("noir", "#1B2448"))
        st = model.Settings(fx={"particles": strength})
        return world.emitter(key, start, end, 99, sp.palette, st, intensity=intensity)

    def test_counts(self):
        self.assertEqual(len(pts.SHAPES_2D), 15)
        self.assertEqual(len(pts.SHAPES_3D), 6)
        self.assertEqual(len(pts.AMBIENT), 26)

    def test_mixed_shapes(self):
        for key, p in pts.PRESETS.items():
            names = pts.shapes_of(p)
            self.assertEqual(names[0], p["shape"], key)
            if p["shape"] in pts.SHAPES_2D:
                first, last = pts.tile_range(p)                  # neighbours in the atlas
                self.assertEqual(last - first + 1, len(names), key)
            else:
                self.assertTrue(all(n in pts.SHAPES_3D for n in names), key)
        which = pts.particle_shapes(pts.PRESETS["shape_confetti"], 7, 400)
        self.assertEqual(set(which.tolist()), set(range(5)))         # every shape is used

    def test_stepped_motion_turns_at_right_angles(self):
        p = pts.PRESETS["circuit"]
        n = len(p["steps"]["axes"])
        life = np.full(400, 3.2)
        age = np.linspace(0.0, 3.2, 400)
        i = np.full(400, 4)                                   # one particle (system 4 % 3), one life
        disp, v = pts._steps(p, age, life, 11, i, np.full(400, 2))
        step = np.diff(disp, axis=0)
        self.assertLessEqual(np.abs(step).max(), p["steps"]["speed"] * (age[1] - age[0]) + 1e-9)     # continuous
        self.assertTrue(((np.abs(step) > 1e-12).sum(axis=1) <= 2).all())    # one axis (two at a boundary)
        self.assertTrue(((np.abs(v) > 0).sum(axis=1) <= 1).all())
        axes = pts.step_axes(p, np.arange(3))
        self.assertEqual(axes.shape, (3, n))
        self.assertEqual(len({tuple(a) for a in axes.tolist()}), 3)          # the 3 systems turn differently

    def test_tail_follows_the_head(self):
        spec = self.spec("circuit")
        s = pts.state(spec, 8.0)
        live = s["alpha"] > 0
        self.assertTrue(live.any())
        dt = spec["preset"]["tail"]["time"] / pts.TAIL_POINTS
        chain = np.concatenate([s["pos"][:, None], s["tail"]], axis=1)[live]
        gap = np.linalg.norm(np.diff(chain, axis=1), axis=2)
        self.assertLessEqual(gap.max(), np.sqrt(3) * spec["preset"]["steps"]["speed"] * dt + 1e-6)

    def test_dot_march_is_evenly_spaced(self):
        spec = self.spec("dot_march", start=0.0, end=40.0)
        s = pts.state(spec, 30.0)
        live = s["alpha"] > 0.9
        for h in spec["preset"]["height"]:
            sel = live & np.isclose(s["pos"][:, 2], h)
            a = np.sort(np.arctan2(s["pos"][sel, 0], s["pos"][sel, 1]))
            gaps = np.diff(a)
            gaps = gaps[gaps < 0.5]                           # leave out the gap between the train's ends
            self.assertGreater(len(gaps), 20)
            self.assertLess(gaps.std(), 1e-6 + gaps.mean() * 0.01, h)

    def test_line_effects(self):
        from lyric_live_builder.core.parts import lines
        for key in ("horizon", "plexus"):
            spec = self.spec(key, start=2.0, end=14.0)
            p = spec["preset"]
            geo = lines.geometry(p, spec["seed"], spec["colors"])
            q = len(geo["width"])
            for v in geo.values():
                self.assertEqual(len(v), q, key)
                self.assertTrue(np.isfinite(v).all(), key)
            times, values = lines.state_keys(spec)              # the track gives progress() exactly
            for t in np.linspace(spec["start"], times[-1], 23):
                np.testing.assert_allclose([np.interp(t, times, [v[c] for v in values]) for c in range(3)],
                                           lines.progress(spec, t), atol=1e-9)
            def shown(t):
                return lines.state(spec, geo, t)[1].reshape(q, 4, 4)[:, 0, 3] > 0
            self.assertGreater(shown(spec["start"] + 1.0).sum(), 0, key)
            self.assertLess(shown(spec["start"] + 0.5).sum(), shown(spec["start"] + 3.0).sum(), key)   # drawn in
            self.assertLess(shown(spec["end"] + 0.8).sum(), shown(spec["end"]).sum(), key)             # erased
            self.assertEqual(shown(times[-1] + 0.01).sum(), 0, key)
            for t in np.arange(spec["start"], spec["end"], 0.7):
                co, _ = lines.state(spec, geo, t)
                self.assertGreater(np.linalg.norm(co - EYE, axis=1).min(), model.MIN_EYE_DISTANCE, key)
        spec = self.spec("plexus")
        geo = lines.geometry(spec["preset"], spec["seed"], spec["colors"])
        self.assertLessEqual(int((geo["dot"] > 0.5).sum()), lines.MAX_POINTS)
        self.assertLessEqual(int((geo["dot"] < 0.5).sum()), lines.MAX_SEGMENTS)
        self.assertGreater(int((geo["dot"] < 0.5).sum()), 20)
        link = spec["preset"]["lines"]["link"]
        for t in (5.0, 9.0):                                 # long links are hidden, short ones shown
            _, col = lines.state(spec, geo, t)
            tau = lines.progress(spec, t)[2]
            seg = geo["dot"] < 0.5
            d = np.linalg.norm(lines.positions(spec["preset"], geo["a"], geo["pa"], tau)
                               - lines.positions(spec["preset"], geo["b"], geo["pb"], tau), axis=1)
            alpha = col.reshape(-1, 4, 4)[:, 0, 3]
            self.assertTrue((alpha[seg & (d >= link)] == 0).all())
            self.assertTrue((alpha[seg & (d < 0.5 * link)] > 0).all())

    def test_second_round_motions(self):
        # rings closing in stop at their smallest radius (life x inward speed), never at the audience
        for key in ("swirl_in", "rising_shards", "closing_panels"):
            spec = self.spec(key)
            p = spec["preset"]
            least = p["radius"][0] - p["radial"] * p["life"][1]
            self.assertGreater(least, 2.4, key)
            for t in np.arange(spec["start"], spec["end"], 0.5):
                s = pts.state(spec, t)
                live = s["alpha"] > 0
                if live.any():
                    r = np.linalg.norm(s["pos"][live, :2], axis=1)
                    self.assertGreaterEqual(r.min(), least - 1e-6, (key, t))
                    if p.get("levels"):
                        self.assertTrue(np.isin(np.round(s["pos"][live, 2], 6), np.round(p["levels"], 6)).all(), key)
        # lasers: from the two floor points, up and inward within the spread, passing well above the audience
        spec = self.spec("lasers")
        p = spec["preset"]
        c = p["cones"]
        seen = 0
        for t in np.arange(spec["start"], spec["end"], 0.25):
            s = pts.state(spec, t)
            live = np.flatnonzero(s["alpha"] > 0)
            for k in live:
                pos, v = s["pos"][k], s["vel"][k]
                side = -1.0 if pos[0] < 0 else 1.0
                self.assertAlmostEqual(abs(pos[0]), c["x"], delta=c["x"] * 0.2)
                d = v / np.linalg.norm(v)
                self.assertGreaterEqual(d @ pts.cone_axis(p, side), math.cos(math.radians(c["spread"])) - 1e-6)
                cross = abs(pos[0]) / max(abs(d[0]), 1e-9)          # where the beam is above the middle
                if cross < p["beam"]["length"]:
                    self.assertGreater(pos[2] + d[2] * cross, 3.0)
                seen += 1
        self.assertGreater(seen, 0)
        # bokeh: faint (opacity), drifting up slowly
        spec = self.spec("bokeh")
        a, b = pts.state(spec, 6.0), pts.state(spec, 6.5)
        self.assertLessEqual(a["alpha"].max(), spec["preset"]["opacity"] + 1e-9)
        live = (a["alpha"] > 0) & (b["alpha"] > 0)
        rise = (b["pos"][live] - a["pos"][live])[:, 2]
        self.assertTrue(live.any() and np.allclose(rise[np.abs(rise) < 0.2], 0.05, atol=1e-6))
        # pops start and end at nothing; slabs take their per-axis sizes
        self.assertEqual(pts.POP_CURVE[1][0], 0.0)
        self.assertEqual(pts.POP_CURVE[1][-1], 0.0)
        s = pts.state(self.spec("slab_tunnel"), 6.0)
        for a, (lo, hi) in enumerate(pts.PRESETS["slab_tunnel"]["size3d"]):
            self.assertTrue(((s["size3"][:, a] >= lo - 1e-9) & (s["size3"][:, a] <= hi + 1e-9)).all())

    def test_every_preset_is_sane(self):
        for key in pts.PRESETS:
            if pts.PRESETS[key]["emitter"] == "lines":
                continue                                     # test_line_effects
            spec = self.spec(key)
            if pts.PRESETS[key]["emitter"] == "burst" and not spec["bursts"]:
                spec["bursts"] = [{"t": 3.0, "origin": [0.0, 3.0, 1.5]}]
                spec["pool"] = pts.burst_capacity(spec["preset"], spec["bursts"])
            alive_any = 0
            for t in np.arange(0.0, 18.0, 0.25):
                s = pts.state(spec, t)
                cap = spec["count"] + spec["pool"]
                self.assertEqual(len(s["pos"]), cap, key)
                for v in s.values():
                    self.assertTrue(np.isfinite(v).all(), key)
                alive = s["alpha"] > 0
                alive_any += alive.sum()
                if alive.any():
                    d = np.linalg.norm(s["pos"][alive] - EYE, axis=1)
                    self.assertGreaterEqual(d.min(), model.MIN_EYE_DISTANCE - 1e-6, (key, t))
                if t < spec["start"] or t > spec["end"] + spec["fade_out"]:
                    self.assertFalse(alive.any(), (key, t))
            self.assertGreater(alive_any, 0, key)

    def test_deterministic(self):
        a, b = self.spec("snow"), self.spec("snow")
        np.testing.assert_array_equal(pts.state(a, 7.3)["pos"], pts.state(b, 7.3)["pos"])

    def test_intensity_and_strength_change_the_amount(self):
        def alive(spec):
            return sum((pts.state(spec, t)["alpha"] > 0).sum() for t in np.arange(6, 12, 0.5))
        low = self.spec("motes", intensity=[(2.0, 0.3), (14.0, 0.3)])
        high = self.spec("motes", intensity=[(2.0, 1.0), (14.0, 1.0)])
        self.assertLess(alive(low), alive(high) * 0.5)
        self.assertLess(self.spec("motes", strength=0.1)["count"], self.spec("motes", strength=0.9)["count"])

    def test_burst_pool_holds_every_live_particle(self):
        spec = self.spec("fireworks")
        self.assertTrue(spec["bursts"])
        for t in np.arange(spec["start"], spec["end"], 0.05):
            n = (pts.state(spec, t)["alpha"] > 0).sum()
            self.assertLessEqual(n, spec["pool"])


class TestLyricParticles(unittest.TestCase):
    """A line's particles "From the Lyrics" (spec §6.2)."""

    def plan(self, particle, line=4, settings=None):
        lines = inputs(12)
        lines[line].particle = particle
        duration = lines[-1].end + 2.0
        return planner.plan(lines, sections_for(duration), duration, 7, bpm=120, settings=settings), lines[line]

    def test_words(self):
        from lyric_live_builder.core import synonyms
        self.assertEqual(synonyms.particles("ホシが降る夜"), ["stars"])
        self.assertEqual(synonyms.particles("STAR light"), ["stars", "motes"])
        self.assertEqual(synonyms.particles("花火があがる"), ["fireworks"])             # not petals
        self.assertEqual(synonyms.particles("桜が舞う"), ["petals"])
        self.assertEqual(synonyms.particles("きみがほしい"), [])                        # not 星
        self.assertEqual(synonyms.particles("窓の外はまだ青くて"), [])

    def test_the_word_picks_the_preset_for_the_line(self):
        p, ln = self.plan("lyrics")                                                 # 光の粒を集めて
        lp = p.lines[4]
        self.assertTrue(any(e["key"] == "motes" and e["start"] == lp.start and e["end"] == lp.end for e in p.emitters))

    def test_no_word_is_planners_choice(self):
        auto, _ = self.plan("", line=0)                                            # 夜明けの色を覚えてる
        lyr, _ = self.plan("lyrics", line=0)
        sig = lambda p: [(e["key"], e["start"], e["end"], e["seed"]) for e in p.emitters]
        self.assertEqual(sig(lyr), sig(auto))

    def test_switched_off_presets_are_skipped(self):
        p, _ = self.plan("lyrics", settings=model.Settings(disabled={"particle": ["motes"]}))
        lp = p.lines[4]
        self.assertFalse(any(e["start"] == lp.start and e["end"] == lp.end and e["key"] == "motes" for e in p.emitters))


class TestAtlasAndMeshes(unittest.TestCase):
    def test_atlas(self):
        a = atlas.draw(256)
        tile = 256 // atlas.GRID
        for k in range(len(pts.SHAPES_2D)):
            r, c = (k // 4) * tile, (k % 4) * tile
            cov = a[r:r + tile, c:c + tile, 3]
            self.assertGreater(cov.mean(), 0.02, pts.SHAPES_2D[k])
            self.assertLess(cov[0].max(), 0.2, pts.SHAPES_2D[k])          # nothing touches the tile edge
        png = atlas.png_bytes(a)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(atlas.tile_uv(0), (0.0, 0.75, 0.25, 1.0))

    def test_dome_faces_inward(self):
        v, f = meshes.dome()
        for a, b, c in f[:200]:
            n = np.cross(v[b] - v[a], v[c] - v[a])
            self.assertLess(np.dot(n, v[a] + v[b] + v[c]), 0)

    def test_builtin_meshes_are_valid(self):
        keys = ["dome", "orb"] + [f"far:{k}" for k in ("moon", "sun", "mountains", "city", "water")] + \
            [f"shape:{k}" for k in pts.SHAPES_3D]
        for key in keys:
            v, f = meshes.build(key)
            self.assertTrue(all(0 <= i < len(v) for face in f for i in face), key)


class TestWorld(unittest.TestCase):
    def test_sections_get_themes_backgrounds_and_particles(self):
        p, b = make(settings=model.Settings(mood="pop", beats=np.arange(0, 120, 0.5)))
        self.assertEqual(len(p.section_plans), len(p.sections))
        self.assertTrue(all(sp.particles for sp in p.section_plans))
        self.assertGreater(len({w["spec"]["key"] for w in p.world}), 1)
        dome = [n for n in b.nodes if n.kind == "dome"]
        self.assertEqual(len(dome), 1)
        self.assertEqual(len(b.emitters), len(p.emitters))
        # the same kind of section reuses its theme most of the time
        by_kind = {}
        for sp in p.section_plans:
            by_kind.setdefault(sp.kind, []).append(sp.theme)
        self.assertTrue(any(len(set(v)) == 1 and len(v) > 1 for v in by_kind.values()))

    def test_dome_shows_the_active_background_between_transitions(self):
        for seed in range(5):
            p, b = make(seed=seed, settings=model.Settings(fx={"world_switch": 1.0}))
            for w0, w1 in zip(p.world, p.world[1:] + [None]):
                t = (w0["t"] + w0["dur"] + (w1["t"] if w1 else p.duration)) / 2
                slot, at = visible_slot(b, t)
                want = bgs.slot_values(world.active_background(p.world, t))
                np.testing.assert_allclose(at(f"dome:top{slot}"), want["top"], atol=1e-5)
                np.testing.assert_allclose(at(f"dome:mode{slot}"), want["mode"], atol=1e-5)

    def test_transitions_never_overlap_and_ramp_both_ways(self):
        p, b = make(seed=3, settings=model.Settings(fx={"world_switch": 1.0}))
        for a, c in zip(p.world, p.world[1:]):
            self.assertGreaterEqual(c["t"], a["t"] + a["dur"] - 1e-9)
        prog = next(x for x in b.tracks if x.prop == "dome:progress")
        self.assertTrue(((prog.values >= -1e-6) & (prog.values <= 1 + 1e-6)).all())

    def test_line_background_override_switches_at_the_line(self):
        p, b = make(seed=2, background="", transition="")
        lines = inputs(24, sec_len=16.0)
        lines[5].background, lines[5].transition = "underwater", "ring"
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(a, c, "verse") for a, c in sections_for(duration, 16.0)]
        p = planner.plan(lines, secs, duration, 2, settings=model.Settings())
        w = next(x for x in p.world if x["spec"]["key"] == "underwater")
        self.assertAlmostEqual(w["t"], lines[5].start, places=6)
        self.assertEqual(w["transition"], "ring")

    def test_section_summary_matches_the_plan(self):
        lines = inputs(24, sec_len=16.0)
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(a, c, "verse") for a, c in sections_for(duration, 16.0)]
        self.assertGreaterEqual(len(secs), 5)
        secs[1].theme, secs[1].background = "morning_garden", "evening"        # the case from the review
        secs[2].theme = secs[3].theme = "under_sea"             # one background for both sections
        last = max(ln.index for ln in lines if ln.section_index == 2)
        lines[last].background = "starry"                       # ...changed by a line: only to the end of 2
        first = min(ln.index for ln in lines if ln.section_index == 4)
        lines[first].start = secs[4].start                      # a line at a section's very start
        lines[first].background = "dawn"
        st = model.Settings()
        p = planner.plan(lines, secs, duration, 5, settings=st)
        summary = world.section_summary(secs, lines, 5, st)
        for s, sp in zip(summary, p.section_plans):
            self.assertEqual(s["theme"], sp.theme)
            self.assertEqual(s["background"], sp.background["key"])
            self.assertEqual(s["particles"], sp.particles)
            self.assertTrue(set(s["particles"]) <= set(themes.THEMES[s["theme"]]["particles"]))
        self.assertEqual(summary[1]["background"], "evening")
        self.assertEqual(summary[1]["background_from"], "section")
        self.assertEqual(summary[1]["theme"], "morning_garden")
        self.assertTrue(summary[1]["theme_set"])
        self.assertEqual((summary[3]["background"], summary[3]["background_from"]), ("underwater", "theme"))
        self.assertEqual((summary[4]["background"], summary[4]["background_from"], summary[4]["line"]),
                         ("dawn", "line", first))
        # the line's background is on from the line to the end of its section, then the next section's is back
        self.assertEqual(world.active_background(p.world, lines[last].start + 1.0)["key"], "starry")
        self.assertEqual(world.active_background(p.world, secs[3].start + 2.0)["key"], "underwater")
        self.assertEqual(summary[0]["background_from"], "theme")
        self.assertFalse(summary[0]["theme_set"])

    def test_line_summary_matches_the_plan(self):
        lines = inputs(24, sec_len=16.0)
        lines[1].background = "starry"                       # section 0 is 0-16 s: lines 0-3
        lines[5].particle = "fireworks"
        lines[7].particle = world.LYRIC_PARTICLES
        lines[7].text = "雪が降る夜に"
        duration = lines[-1].end + 2.0
        secs = [model.SectionInput(a, c, "verse") for a, c in sections_for(duration, 16.0)]
        st = model.Settings()
        p = planner.plan(lines, secs, duration, 5, settings=st)
        summary = world.line_summary(secs, lines, 5, st)
        self.assertEqual(len(summary), len(lines))
        line_emitters = {}
        for e in p.emitters:
            for lp in p.lines:
                if abs(e["start"] - lp.start) < 1e-9 and abs(e["end"] - lp.end) < 1e-9:
                    line_emitters[lp.index] = e["key"]
        for ln, s in zip(lines, summary):
            self.assertEqual(s["section"], ln.section_index)
            want = world.active_background(p.world, ln.start + 0.01)["key"] if s["background_from"] != "this" \
                else ln.background
            self.assertEqual(s["background"], want, ln.index)
            self.assertEqual(s["added"], line_emitters.get(ln.index, ""), ln.index)
        self.assertEqual((summary[1]["background"], summary[1]["background_from"]), ("starry", "this"))
        self.assertEqual((summary[2]["background"], summary[2]["background_from"], summary[2]["line"]),
                         ("starry", "line", 1))                                     # on to the section end
        self.assertNotEqual(summary[4]["background_from"], "line")                  # the next section's own
        self.assertEqual((summary[5]["added"], summary[5]["added_auto"]), ("fireworks", False))
        self.assertEqual(summary[7]["added"], "snow")                                # from the lyrics

    def test_strong_flashes_are_spaced(self):
        for seed in range(6):
            lines = inputs(30, gap=1.0, sec_len=8.0)
            for ln in lines:
                ln.impact = True
            duration = lines[-1].end + 2.0
            secs = [model.SectionInput(a, c, "chorus") for a, c in sections_for(duration, 8.0)]
            p = planner.plan(lines, secs, duration, seed, settings=model.Settings(mood="pop", fx={"world_switch": 1.0}))
            strong = sorted([e["t"] for e in p.events if e["type"] == "flash" and e["amp"] >= world.STRONG] +
                            [w["t"] + w["dur"] / 2 for w in p.world if bgs.TRANSITIONS.get(w["transition"], {}).get("flash")])
            for a, c in zip(strong, strong[1:]):
                self.assertGreaterEqual(c - a, world.FLASH_GAP - 1e-9, seed)
            for t in np.arange(0, duration, 0.25):
                self.assertLessEqual(sum(1 for x in strong if t <= x < t + 1.0), 3)

    def test_change_only_particles(self):
        base = {"mood": "calm", "style": "paper", "fx": {}, "disabled": {}, "accent": "", "seed": 7, "stage_offsets": {}}
        new = omakase.reroll(base, "particles", Rng(5))
        p1, _ = make(settings=omakase.settings(base))
        p2, _ = make(settings=omakase.settings(new))
        self.assertEqual([(x.layout, x.enter, x.exit, x.anchor) for x in p1.lines],
                         [(x.layout, x.enter, x.exit, x.anchor) for x in p2.lines])
        self.assertEqual([w["spec"]["key"] for w in p1.world], [w["spec"]["key"] for w in p2.world])
        self.assertNotEqual([(e["key"], e["seed"]) for e in p1.emitters], [(e["key"], e["seed"]) for e in p2.emitters])

    def test_change_only_background(self):
        base = {"mood": "pop", "style": "magenta", "fx": {"world_switch": 1.0}, "disabled": {}, "accent": "",
                "seed": 11, "stage_offsets": {}}
        new = omakase.reroll(base, "background", Rng(5))
        p1, _ = make(settings=omakase.settings(base))
        p2, _ = make(settings=omakase.settings(new))
        self.assertEqual([x.layout for x in p1.lines], [x.layout for x in p2.lines])
        self.assertNotEqual([(w["spec"]["key"], w["transition"]) for w in p1.world],
                            [(w["spec"]["key"], w["transition"]) for w in p2.world])

    def test_rerolling_one_line_changes_only_that_line(self):
        lines = inputs(24, sec_len=16.0)
        duration = lines[-1].end + 2.0
        secs = sections_for(duration, 16.0)
        a = planner.plan(lines, secs, duration, 4)
        lines[6].seed_offset = 1
        b = planner.plan(lines, secs, duration, 4)
        diff = [i for i, (x, y) in enumerate(zip(a.lines, b.lines))
                if (x.layout, x.enter, x.hold, x.exit, x.distance, x.anchor) != (y.layout, y.enter, y.hold, y.exit, y.distance, y.anchor)]
        self.assertEqual(diff, [6])

    def test_koma_steps_the_text(self):
        p, b = make(n_lines=4, settings=model.Settings(fx={"koma": 8}))
        glyph = next(n for n in b.nodes if n.kind == "glyph")
        tr = [x for x in b.tracks if x.node == glyph.id and x.prop in ("location", "scale", "color")]
        self.assertTrue(tr and all(x.interp == "constant" for x in tr))
        steps = np.diff(tr[0].times)
        self.assertTrue(np.all(np.abs(steps / 0.125 - np.round(steps / 0.125)) < 0.05))

    def test_motion_strength(self):
        def travel(motion):
            lines = inputs(4)
            for ln in lines:
                ln.enter, ln.layout = "fly_in", "front"
            p = planner.plan(lines, sections_for(20.0), 20.0, 3, settings=model.Settings(fx={"motion": motion}))
            b = bake.bake(p, metrics)
            loc = next(x for x in b.tracks if x.prop == "location" and "_g" in x.node)
            return np.ptp(loc.values, axis=0).max()
        self.assertLess(travel(0.1), travel(1.0))


class TestGuide(unittest.TestCase):
    def test_guides_only_for_lines_away_from_the_gaze(self):
        lines = inputs(16, is_3d=True)
        for k, ln in enumerate(lines):
            ln.layout, ln.persist = ("floor" if k % 2 else "front"), "next"
        duration = lines[-1].end + 2.0
        p = planner.plan(lines, sections_for(duration), duration, 7, settings=model.Settings(fx={"guide": 0.7}))
        b = bake.bake(p, metrics)
        self.assertGreaterEqual(len(b.guides), 6)
        self.assertTrue(all(lines[g["line"]].layout == "floor" or g["angle"] >= guide.ANGLE for g in b.guides))
        for g in b.guides:
            self.assertGreaterEqual(g["angle"], guide.ANGLE - 1e-9)
        ts = [g["t_hit"] for g in b.guides]
        self.assertTrue(all(c - a >= guide.MIN_GAP - 1e-9 for a, c in zip(ts, ts[1:])))
        # the lead mote arrives where the line appears, when it appears
        g = b.guides[0]
        n = b.guides.index(g)
        loc = next(x for x in b.tracks if x.node == f"guide{n:03d}_m0" and x.prop == "location")
        at_hit = EYE + np.array([np.interp(g["t_hit"], loc.times, loc.values[:, c]) for c in range(3)])  # under the eye pivot
        self.assertLess(np.linalg.norm(at_hit - np.array(g["target"])), 0.05)

    def test_line_settings_and_strength(self):
        _, b = make(n_lines=12, settings=model.Settings(fx={"guide": 0.0}))
        self.assertEqual(b.guides, [])
        _, on = make(n_lines=12, guide="on")
        self.assertEqual(len(on.guides) >= 6, True)
        _, off = make(n_lines=12, guide="off", persist="section")
        self.assertEqual(off.guides, [])

    def test_always_guide_has_a_streak_and_lead_grows_with_the_arc(self):
        p, b = make(n_lines=12, guide="on")
        for g in b.guides:
            u = np.array(g["from"]) - EYE
            arc = guide._angle(u, np.array(g["target"]) - EYE)
            self.assertGreaterEqual(arc, guide.MIN_ARC - 1e-6)
            self.assertAlmostEqual(g["t_hit"] - g["t_on"], guide.lead(arc), places=5)
        self.assertLess(guide.lead(guide.MIN_ARC), guide.lead(math.pi))
        self.assertEqual(guide.lead(math.pi), guide.LEAD_MAX)
        for g in bake.bake(p, metrics, udon=True).guides:
            self.assertAlmostEqual(g["t_hit"] - g["t_on"], guide.LEAD_MAX + guide.UDON_HOLD)

    def test_guides_ignore_particle_rerolls(self):
        base = {"mood": "emotional", "style": "noir", "fx": {}, "disabled": {}, "accent": "", "seed": 9, "stage_offsets": {}}
        _, b1 = make(persist="section", settings=omakase.settings(base))
        _, b2 = make(persist="section", settings=omakase.settings(omakase.reroll(base, "particles", Rng(1))))
        self.assertEqual([(g["line"], g["t_hit"], g["kinds"]) for g in b1.guides],
                         [(g["line"], g["t_hit"], g["kinds"]) for g in b2.guides])

    def test_dome_light_for_a_line_behind(self):
        """A line behind the estimated gaze gets the dome cue: direction and a ramp to 1 at the hit."""
        from types import SimpleNamespace as NS
        lines = [NS(index=0, start=1.0, end=6.0, guide="", colors=None, emphasis=False),
                 NS(index=1, start=5.0, end=9.0, guide="", colors=None, emphasis=False)]
        plan = NS(lines=lines, fx={"guide": 0.7})
        front, behind = EYE + [0.0, 3.5, 0.0], EYE + [0.0, -3.5, 0.0]

        def positions(t):
            out = {"line000_g00": front} if 1.0 <= t < 6.0 else {}
            if t >= 5.0:
                out["line001_g00"] = behind
            return out
        on = lambda t0: model.Track("", "active", "constant", np.array([0.0, t0], np.float32), np.array([[0.0], [1.0]], np.float32))
        tracks = {("line000_g00", "active"): on(1.0), ("line001_g00", "active"): on(5.0)}
        g = guide.plan_guides(plan, positions, tracks)
        self.assertEqual(len(g), 1)
        self.assertIn("dome", g[0]["kinds"])
        self.assertAlmostEqual(g[0]["angle"], math.pi, places=3)
        world_plan = NS(world=[{"t": 0.0, "dur": 0.0, "spec": bgs.resolve("night"), "transition": ""}], events=[])
        _, tr = bake_world.dome(world_plan, g)
        cue = next(x for x in tr if x.prop == "dome:cue_amount")
        self.assertAlmostEqual(float(np.interp(5.0, cue.times, cue.values[:, 0])), 1.0, places=5)
        direction = next(x for x in tr if x.prop == "dome:cue_dir")
        np.testing.assert_allclose(direction.values[-1], [0.0, -1.0, 0.0], atol=1e-5)

    def test_line_bursts_start_after_the_text(self):
        lines = inputs(12)
        for ln in lines:
            ln.impact = True
        p = planner.plan(lines, sections_for(60.0), 60.0, 5)
        for e in p.emitters:
            for bu in e["bursts"]:
                if e["key"] == "sparkle_burst":
                    ln = min(p.lines, key=lambda x: abs(x.start - bu["t"]))
                    self.assertGreater(bu["t"], ln.start)


class TestOmakase(unittest.TestCase):
    def test_omakase_rolls_everything_but_keeps_the_rest(self):
        state = {"mood": "calm", "style": "paper", "fx": {"guide": 0.3}, "disabled": {}, "accent": "", "seed": 1,
                 "stage_offsets": {"2": 3}}
        a = omakase.omakase(state, Rng(42))
        b = omakase.omakase(state, Rng(42))
        self.assertEqual(a, b)
        self.assertNotEqual(a["mood"], "calm")
        self.assertIn(a["style"], styles.STYLES)
        self.assertEqual(a["stage_offsets"], {})
        self.assertEqual(a["fx"]["guide"], 0.3)                   # the comfort setting is the user's
        for kind, minimum in omakase.MIN_ON.items():
            total = len(omakase._items(kind))
            self.assertGreaterEqual(total - len(a["disabled"][kind]), min(minimum, total), kind)
        self.assertNotIn("still", a["disabled"]["hold"])

    def test_moods_cycle_and_targets(self):
        seen = set()
        state = {"mood": "", "style": "", "fx": {}, "disabled": {}, "accent": "", "seed": 1, "stage_offsets": {}}
        rnd = Rng(3)
        for _ in range(40):
            state = omakase.omakase(state, rnd)
            seen.add(state["mood"])
        self.assertEqual(seen, set(moods.ORDER) - set(moods.STICKY))       # horror is never rolled
        r = omakase.reroll(state, "text", rnd)
        self.assertEqual(r["stage_offsets"], {"2": 1})
        self.assertEqual({k: v for k, v in r.items() if k != "stage_offsets"},
                         {k: v for k, v in state.items() if k != "stage_offsets"})


    def test_horror_is_the_users_choice(self):
        rnd = Rng(5)
        state = {"mood": "pop", "style": "", "fx": {}, "disabled": {}, "accent": "", "seed": 1, "stage_offsets": {}}
        for _ in range(60):
            state = omakase.omakase(state, rnd)
            self.assertNotEqual(state["mood"], "horror")
            self.assertFalse(state["style"].startswith("hr_"), state["style"])     # horror styles: horror only
        state["mood"] = "horror"
        for _ in range(10):
            state = omakase.omakase(state, rnd)
            self.assertEqual(state["mood"], "horror")                            # kept once chosen
            self.assertIn(state["style"], moods.MOODS["horror"]["styles"] + tuple(
                k for k in styles.ORDER if "horror" in styles.STYLES[k].get("moods", ("horror",))))

    def test_part_groups_follow_the_mood(self):
        from lyric_live_builder.core import registry
        lines = inputs(24)
        duration = lines[-1].end + 2.0
        for mood, banned in (("calm", ("kinetic", "typo", "horror")), ("pop", ("typo", "horror")),
                             ("editorial", ("kinetic", "horror")), ("horror", ("kinetic", "typo"))):
            p = planner.plan(lines, sections_for(duration), duration, 7, bpm=120, settings=model.Settings(mood=mood))
            used = {registry.get(kind, getattr(lp, kind)).group for lp in p.lines for kind in ("enter", "hold", "exit")}
            self.assertFalse(used & set(banned), (mood, used))
        lines[2].hold = "hr_twitch"                                                 # set by hand: always used
        p = planner.plan(lines, sections_for(duration), duration, 7, bpm=120, settings=model.Settings(mood="calm"))
        self.assertEqual(p.lines[2].hold, "hr_twitch")


class TestAudioSpectrum(unittest.TestCase):
    def test_tone_lands_in_its_band(self):
        sr = 22050
        t = np.arange(sr * 3) / sr
        x = (np.sin(2 * np.pi * 1000 * t) * (0.2 + 0.8 * (t > 1.5))).astype(np.float32)
        info = audio.analyze(x, sr)
        self.assertEqual(info.spectrum.shape[1], audio.BANDS)
        edges = np.geomspace(40.0, min(16000.0, sr / 2), audio.BANDS + 1)
        band = int(np.searchsorted(edges, 1000.0) - 1)
        loud = info.spectrum[-20:]
        self.assertEqual(int(loud.mean(axis=0).argmax()), band)


class TestSpeed(unittest.TestCase):
    def test_four_minutes(self):
        t = time.perf_counter()
        make(n_lines=60, sec_len=30.0, settings=model.Settings(mood="chaos", beats=np.arange(0, 250, 0.5)))
        self.assertLess(time.perf_counter() - t, 15.0)


if __name__ == "__main__":
    unittest.main()
