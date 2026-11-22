"""Phase 2 core: part contracts, layouts, planner and bake (no Blender)."""
import math
import time
import unittest

import numpy as np

from lyric_live_builder.core import bake, lyrics, model, planner, registry, xform
from lyric_live_builder.core.rng import Rng


class FakeMetrics:
    def advance_em(self, ch):
        return 0.3 if ch.isspace() else 0.55 if lyrics.is_latin(ch) else 1.0

    def vadvance_em(self, ch):
        return 1.0


def metrics(role):
    return FakeMetrics()


LYRICS = ["夜明けの色を覚えてる", "ほどけた声が遠くで鳴った", "ねえ、まだ間に合うかな", "透明なままじゃ終われない",
          "光の粒を集めて", "きみの名前を呼ぶよ", "Hello world again", "窓の外はまだ青くて"]


def inputs(n_lines=24, gap=4.0, is_3d=False, sec_len=32.0, **over):
    # whole lines (cuts=1) unless a test asks: at the text size these lines would be cut into parts, which
    # tests/core/test_cuts.py checks on its own
    over.setdefault("cuts", 1)
    out = []
    for i in range(n_lines):
        text = LYRICS[i % len(LYRICS)]
        s = 2.0 + i * gap
        ct = [s + k * 0.12 for k in range(len(text))]
        out.append(model.LineInput(index=i, text=text, start=s, end=s + gap, section_index=int(s // sec_len),
                                   char_times=ct, emph_words=["透明"] if "透明" in text else [], is_3d=is_3d, **over))
    return out


def sections_for(duration, sec_len=32.0):
    n = int(math.ceil(duration / sec_len))
    return [(k * sec_len, min(duration, (k + 1) * sec_len)) for k in range(n)]


def make(n_lines=24, seed=7, sec_len=32.0, **kw):
    lines = inputs(n_lines, sec_len=sec_len, **kw)
    duration = lines[-1].end + 2.0
    p = planner.plan(lines, sections_for(duration, sec_len), duration, seed, bpm=120)
    return p, bake.bake(p, metrics)


class TestContracts(unittest.TestCase):
    def ctx(self, n=6):
        return registry.MotionCtx(n=n, rest=np.zeros((n, 3)), em=0.2, start=1.0, end=5.0,
                                  char_times=np.linspace(1, 2, n), bpm=120, seed=3)

    def assert_identity(self, d, msg):
        np.testing.assert_allclose(d.loc, 0, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(np.abs(d.rot[..., 0]), 1, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(d.scale, 1, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(d.alpha, 1, atol=1e-9, err_msg=msg)
        np.testing.assert_allclose(d.mask, 1, atol=1e-9, err_msg=msg)

    def test_counts(self):
        self.assertEqual(len(registry.keys("enter")), 74)
        self.assertEqual(len(registry.keys("hold")), 45)
        self.assertEqual(len(registry.keys("exit")), 63)
        self.assertEqual(len([p for p in registry.parts("layout") if not p.only_3d]), 62)
        self.assertEqual(len([p for p in registry.parts("layout") if p.only_3d]), 6)

    def test_enter_identity_at_1_and_hidden_or_moved_at_0(self):
        c = self.ctx()
        for part in registry.parts("enter"):
            self.assert_identity(part.evaluate(c, np.ones((6, 3))), part.key)
            d0 = part.evaluate(c, np.zeros((6, 3)))
            changed = (d0.alpha < 0.5).any() or (np.abs(d0.scale - 1) > 0.1).any() or (np.abs(d0.loc) > 1e-3).any() \
                or (d0.mask < 0.5).any()
            self.assertTrue(changed, part.key)

    def test_exit_identity_at_0(self):
        c = self.ctx()
        for part in registry.parts("exit"):
            self.assert_identity(part.evaluate(c, np.zeros((6, 3))), part.key)
            d1 = part.evaluate(c, np.ones((6, 3)))
            gone = (d1.alpha < 0.05).all() or (np.abs(d1.scale) < 0.05).all()
            self.assertTrue(gone, part.key)

    def test_hold_identity_at_0_and_finite(self):
        c = self.ctx()
        for part in registry.parts("hold"):
            self.assert_identity(part.evaluate(c, np.zeros((6, 3))), part.key)
            d = part.evaluate(c, np.linspace(0, 30, 90)[None].repeat(6, 0))
            self.assertTrue(np.isfinite(d.loc).all() and np.isfinite(d.rot).all(), part.key)

    def test_no_motion_comes_toward_the_viewer(self):
        c = self.ctx()
        p = np.linspace(0, 1, 21)[None].repeat(6, 0)
        for kind in ("enter", "exit"):
            for part in registry.parts(kind):
                self.assertGreaterEqual(part.evaluate(c, p).loc[..., 1].min(), -1e-9, part.key)
        s = np.linspace(0, 20, 120)[None].repeat(6, 0)
        for part in registry.parts("hold"):
            self.assertGreaterEqual(part.evaluate(c, s).loc[..., 1].min(), -1e-9, part.key)

    def test_word_holds_move_words_together(self):
        n = 6
        c = registry.MotionCtx(n=n, rest=np.zeros((n, 3)), em=0.2, start=1.0, end=5.0, char_times=np.linspace(1, 2, n),
                               bpm=120, seed=3, words=np.array([0, 0, 0, 1, 1, 1]))
        s = np.linspace(0, 6, 60)[None].repeat(n, 0)
        d = registry.get("hold", "kn_word_pulse").evaluate(c, s)
        same = np.abs(d.scale[0, :, 0] - d.scale[1, :, 0]).max() < 1e-9
        apart = np.abs(d.scale[0, :, 0] - d.scale[3, :, 0]).max() > 0.01
        self.assertTrue(same and apart)

    def test_masked_glyphs_get_mask_tracks(self):
        lines = inputs(4)
        lines[0].enter, lines[1].enter, lines[2].enter = "wipe", "checker", "fade"
        lines[2].exit = lines[1].exit = "fade"
        lines[0].layout = "front"                       # upright glyphs: their boxes are one region, shifted
        duration = lines[-1].end + 2.0
        p = planner.plan(lines, sections_for(duration), duration, 7, bpm=120)
        b = bake.bake(p, metrics)
        by = {}
        for t in b.tracks:
            by.setdefault((t.node.split("_")[0], t.prop), []).append(t)
        self.assertIn(("line000", "mask"), by)
        self.assertNotIn(("line002", "mask"), by)                        # no mask, no tracks
        mask = by[("line000", "mask")][0]
        self.assertAlmostEqual(float(mask.values[0, 0]), 0.0, places=3)
        self.assertAlmostEqual(float(mask.values[-1, 0]), 1.0, places=3)
        shape = by[("line001", "mask_shape")][0]
        self.assertEqual(float(shape.values[0, 0]), 3.0)                 # checker
        box = by[("line000", "mask_box")][0].values[0]
        self.assertTrue(box[0] < -0.5 and box[2] > 0.5 and box[1] < -0.5 and box[3] > 0.5)   # wider than the glyph
        # the boxes of one line describe the same region: shifted by each glyph's place
        boxes = [t.values[0] for t in by[("line000", "mask_box")]]
        widths = {round(float(x[2] - x[0]), 3) for x in boxes}
        self.assertEqual(len(widths), 1)

    def test_slice_copies_and_line_planes(self):
        lines = inputs(4)
        lines[0].enter, lines[1].enter, lines[2].enter = "slice", "wipe", "checker"
        lines[3].enter = "fade"
        duration = lines[-1].end + 2.0
        b = bake.bake(planner.plan(lines, sections_for(duration), duration, 7, bpm=120), metrics)
        copies = [n for n in b.nodes if bake.is_band_copy(n.id)]
        real = [n for n in b.nodes if n.kind == "glyph" and n.id.startswith("line000") and not bake.is_band_copy(n.id)]
        self.assertEqual(len(copies), 7 * len(real))
        self.assertTrue(all(n.id.startswith("line000") for n in copies))
        tr = {(t.node, t.prop): t for t in b.tracks}
        c0 = copies[0].id
        self.assertEqual(float(tr[(c0, "mask_shape")].values[0, 0]), 4.0)          # one band only
        x = tr[(c0, "location")].values[:, 0]
        self.assertGreater(abs(x[0] - x[-1]), 0.5)                                # slides in from aside
        on = tr[(c0, "active")]
        self.assertEqual(float(on.values[-1, 0]), 0.0)                           # gone once landed
        planes = {n.id: n for n in b.nodes if n.kind == "line_fx"}
        self.assertEqual(set(planes), {"line001_fx", "line002_fx"})
        self.assertEqual([float(tr[(f, "mask_shape")].values[0, 0]) for f in sorted(planes)], [1.0, 3.0])
        self.assertFalse(any(bake.is_band_copy(k) for k in bake.world_positions(b, lines[0].start + 0.2)))

    def test_exit_copies_planes_and_windows(self):
        lines = inputs(4)
        for ln, ex in zip(lines, ("slice", "wipe", "sink", "fade")):
            ln.exit = ex
        duration = lines[-1].end + 2.0
        p = planner.plan(lines, sections_for(duration), duration, 7, bpm=120)
        b = bake.bake(p, metrics)
        copies = [n for n in b.nodes if bake.is_band_copy(n.id)]
        real = [n for n in b.nodes if n.kind == "glyph" and n.id.startswith("line000") and not bake.is_band_copy(n.id)]
        self.assertEqual(len(copies), 7 * len(real))
        self.assertTrue(all(n.id.startswith("line000") and n.id.rsplit("_s", 1)[1] >= "100" for n in copies))
        tr = {(t.node, t.prop): t for t in b.tracks}
        on = tr[(copies[0].id, "active")]
        self.assertAlmostEqual(float(on.times[-1]), p.lines[0].end, places=3)              # until the line ends
        x = tr[(copies[0].id, "location")].values[:, 0]
        self.assertGreater(abs(x[-1] - x[0]), 0.5)                                         # flies out aside
        self.assertIn("line001_fxo", {n.id for n in b.nodes if n.kind == "line_fx"})       # the wipe's bar
        shape = tr[("line002_g00", "mask_shape")]
        self.assertEqual(float(shape.values[-1, 0]), 9.0)                                 # a window from the exit
        box = tr[("line002_g00", "mask_box")].values[-1]
        self.assertAlmostEqual(float(box[1]), -0.66, places=3)                            # the glyph's own frame
        m = tr[("line002_g00", "mask")].values[:, 0]
        self.assertLess(float(m[-1]), 0.05)

    def test_word_of(self):
        self.assertEqual(bake._word_of("光の粒を集めて", ["光の粒を", "集めて"]), [0, 0, 0, 0, 1, 1, 1])


class TestLayouts(unittest.TestCase):
    def ctx(self, text="夜明けの色を覚えてる", distance=3.5, is_3d=True, anchor=(0.0, 0.0)):
        m = FakeMetrics()
        em = 2 * distance * math.tan(math.radians(model.text_angle("mid")) / 2)
        return registry.LayoutCtx(text=text, adv=[m.advance_em(c) for c in text], vadv=[1.0] * len(text),
                                  em=em, distance=distance, eye=1.5, is_3d=is_3d, depth=0.15,
                                  chunks=lyrics.chunk_text(text), char_times=[float(i) for i in range(len(text))],
                                  anchor=anchor)

    def test_every_layout_places_every_visible_char(self):
        for part in registry.parts("layout"):
            c = self.ctx()
            params = part.plan(Rng(1), c)
            pl = part.place(c, params)
            self.assertEqual(sorted(g.char_index for g in pl.glyphs), list(range(len(c.text))), part.key)
            self.assertGreater(pl.em, 0.01, part.key)

    def test_layouts_place_every_glyph_without_overlap(self):
        texts = ["光", "夜明け", "光の粒を集めて", "夜明けの色を覚えてる", "君の名前を呼んだら世界が少しだけ変わった",
                 "Hello my friend", "ありがとう、またね。"]
        for part in registry.parts("layout"):
            for text in texts:
                if not part.fits(len(text.replace(" ", ""))):
                    continue
                for seed in range(3):
                    c = self.ctx(text=text)
                    params = part.plan(Rng(seed + 1), c)
                    pl = part.place(c, params)
                    msg = f"{part.key} {text} {seed}"
                    self.assertEqual(sorted(g.char_index for g in pl.glyphs),
                                     [i for i, ch in enumerate(text) if not ch.isspace()], msg)
                    loc = np.array([g.loc for g in pl.glyphs])
                    size = np.array([g.size for g in pl.glyphs]) * pl.em
                    self.assertTrue(np.isfinite(loc).all(), msg)
                    shown = part.shown(c, params, pl)
                    for a in range(len(loc)):
                        for b in range(a + 1, len(loc)):
                            if shown and (shown[a][1] <= shown[b][0] or shown[b][1] <= shown[a][0]):
                                continue                                          # never on stage together
                            self.assertGreater(np.linalg.norm(loc[a] - loc[b]), 0.45 * min(size[a], size[b]), msg)

    def test_front_size_is_the_visual_angle(self):
        c = self.ctx(text="あ", distance=3.5)                # one letter: never wider than MAX_LINE_ANGLE (docs)
        pl = registry.get("layout", "front").place(c, {})
        self.assertAlmostEqual(pl.em, model.text_em("mid"))
        self.assertAlmostEqual(math.degrees(2 * math.atan(pl.em / 2 / 3.5)), model.TEXT_ANGLE["mid"] * model.TEXT_SCALE)
        np.testing.assert_allclose(pl.loc, [0, 3.5, 1.5], atol=1e-9)
        # the face (-y) points back at the eye
        np.testing.assert_allclose(xform.rotate(pl.rot, [0, -1, 0]), [0, -1, 0], atol=1e-9)

    def test_text_size_settings(self):
        keep = model.TEXT_SCALE
        try:
            base = {d: model.text_em(d) for d in model.DISTANCE}
            model.TEXT_SCALE = keep * 1.25                   # relative: holds whatever the setting is
            for d in model.DISTANCE:                         # the one knob scales the angle of every layer
                self.assertAlmostEqual(model.text_angle(d), keep * 1.25 * model.TEXT_ANGLE[d])
                self.assertGreater(model.text_em(d), base[d])
            self.assertAlmostEqual(model.text_angle("mid", True), model.text_angle("mid") * model.EMPH_FACTOR)
        finally:
            model.TEXT_SCALE = keep

    def test_long_line_is_shrunk_to_70_degrees(self):
        c = self.ctx(text="あ" * 60, distance=1.2)
        pl = registry.get("layout", "front").place(c, {})
        half = 60 * pl.em / 2
        self.assertLessEqual(math.degrees(2 * math.atan(half / 1.2)), 70.0 + 1e-6)

    def test_side_anchor_faces_the_eye(self):
        az = math.radians(62)
        c = self.ctx(anchor=(az, 0.0))
        pl = registry.get("layout", "front").place(c, {})
        to_eye = np.array([0, 0, 1.5]) - pl.loc
        face = xform.rotate(pl.rot, [0, -1, 0])
        np.testing.assert_allclose(face, to_eye / np.linalg.norm(to_eye), atol=1e-9)

    def test_floor_faces_up(self):
        c = self.ctx()
        pl = registry.get("layout", "floor").place(c, {"distance": 2.0})
        np.testing.assert_allclose(xform.rotate(pl.rot, [0, -1, 0]), [0, 0, 1], atol=1e-9)
        self.assertLess(pl.loc[2], 0.2)

    def test_pillar_is_vertical(self):
        c = self.ctx(text="夜明けの色")
        pl = registry.get("layout", "pillar").place(c, {"side": 1, "azimuth": 0.5})
        zs = [g.loc[2] for g in pl.glyphs]
        self.assertEqual(zs, sorted(zs, reverse=True))


    def test_cube_shows_one_face_at_a_time(self):
        c = self.ctx(text="夜明けの色を覚えてる光の粒")
        part = registry.get("layout", "cube")
        params = part.plan(Rng(1), c)
        pl = part.place(c, params)
        shown = part.shown(c, params, pl)
        faces = [params["face_of"][g.char_index] for g in pl.glyphs]
        self.assertGreater(len(set(faces)), 1)
        mid = (shown[faces.index(1)][0] + shown[faces.index(1)][1]) / 2 + 0.4   # face 1 settled in front
        for f, (on, off) in zip(faces, shown):
            self.assertEqual(on <= mid < off, f == 1, f)

    def test_approach_passes_beside_over_the_whole_line(self):
        c = self.ctx(text="夜明けの色")
        c.span = (10.0, 14.0)
        part = registry.get("layout", "approach")
        params = part.plan(Rng(1), c)
        pl = part.place(c, params)
        loc, _ = part.group_motion(c, params, pl, np.array([10.0, 12.0, 14.0]))
        self.assertGreater(loc[0, 1], 20)            # far ahead at the start
        self.assertTrue(0 < loc[1, 1] < loc[0, 1])   # still on its way half-way through
        self.assertLess(loc[2, 1], 0)                # behind the viewer at the end
        self.assertGreater(abs(loc[0, 0]) - sum(c.adv) * pl.em / 2, 1.0)   # never through the viewer


class TestPlanBake(unittest.TestCase):
    def test_deterministic(self):
        a, ba = make(seed=11)
        b, bb = make(seed=11)
        self.assertEqual([(x.layout, x.enter, x.hold, x.exit, x.distance, x.persist) for x in a.lines],
                         [(x.layout, x.enter, x.hold, x.exit, x.distance, x.persist) for x in b.lines])
        self.assertEqual(len(ba.tracks), len(bb.tracks))
        for x, y in zip(ba.tracks, bb.tracks):
            self.assertEqual((x.node, x.prop), (y.node, y.prop))
            np.testing.assert_array_equal(x.values, y.values)
        c, _ = make(seed=12)
        self.assertNotEqual([x.layout for x in a.lines], [x.layout for x in c.lines])

    def test_every_line_in_the_middle_layer(self):
        # the distance layer is no longer chosen (spec §7.1): only layouts with their own place stand nearer
        for seed in range(6):
            p, _ = make(seed=seed, is_3d=seed % 2 == 1)
            for ln in (c for x in p.lines for c in x.cuts or [x]):
                want = registry.get("layout", ln.layout).fixed_distance or "mid"
                self.assertEqual(ln.distance, want, (seed, ln.layout))

    def test_overrides_are_kept(self):
        p, _ = make(n_lines=6, is_3d=True, layout="slanted_wall", enter="fade", hold="float", exit="topple")
        for ln in p.lines:
            self.assertEqual((ln.layout, ln.enter, ln.hold, ln.exit, ln.distance), ("slanted_wall", "fade", "float", "topple", "mid"))
        p, _ = make(n_lines=6, persist="section")
        self.assertTrue(all(ln.persist for ln in p.lines))
        self.assertEqual(len({ln.anchor for ln in p.lines if ln.section_index == 0}),
                         len([ln for ln in p.lines if ln.section_index == 0]))

    def test_kept_line_goes_up_then_aside(self):
        # a kept line appears in front, moves up above the front as the next line comes in, and on to its side slot
        # (shrunk to KEPT_LINE_ANGLE wide) when the next kept line comes up (design §7.2)
        p, b = make(n_lines=6, persist="section")
        eye = np.array([0, 0, model.EYE_HEIGHT])

        def where(ln, t):
            pos = np.array([v for k, v in bake.world_positions(b, t).items() if k.startswith(f"line{ln.index:03d}_")])
            c = pos.mean(axis=0) - eye
            u = (pos - eye) / np.linalg.norm(pos - eye, axis=1)[:, None]
            widest = math.degrees(max(math.acos(min(1.0, float(a @ c_))) for a in u for c_ in u))
            return math.atan2(c[0], c[1]), math.atan2(c[2], math.hypot(c[0], c[1])), widest
        for ln in p.lines[:-1]:
            self.assertIsNotNone(ln.glide, ln.index)
            az, el, _ = where(ln, ln.glide[0] - 0.02)
            self.assertAlmostEqual(az, 0.0, delta=0.05, msg=ln.index)
            self.assertAlmostEqual(el, 0.0, delta=0.12, msg=ln.index)
            az, el, _ = where(ln, ln.glide[1] + 0.05)
            self.assertAlmostEqual(az, 0.0, delta=0.05, msg=ln.index)
            self.assertAlmostEqual(el, math.radians(model.KEEP_ABOVE), delta=0.12, msg=ln.index)
        aside = [ln for ln in p.lines if ln.aside]
        self.assertEqual(len(aside), len(p.lines) - 2)            # all but the last one above and the one in front
        for ln in aside:
            az, el, width = where(ln, ln.aside[1] + 0.05)
            self.assertAlmostEqual(az, ln.anchor[0], delta=0.05, msg=ln.index)
            self.assertLessEqual(width, model.KEPT_LINE_ANGLE + 2.0, ln.index)
        self.assertIsNone(p.lines[-1].glide)              # nothing comes after it in its section
        self.assertIsNone(p.lines[-2].aside)              # the last one kept waits above until the section ends

    def test_2d_lines_never_get_3d_layouts(self):
        for seed in range(5):
            p, _ = make(seed=seed)
            self.assertFalse(any(registry.get("layout", ln.layout).only_3d for ln in p.lines))

    def test_no_overlap_and_eye_distance(self):
        # the layouts and slots keep lines apart at their own sizes; evened out (model.EVEN_ANGLE) lines may grow
        # past the view and meet (the reviewer's choice), but never come closer to the eye than MIN_EYE_DISTANCE
        for even in (None, model.EVEN_ANGLE):
            saved, model.EVEN_ANGLE = model.EVEN_ANGLE, even
            try:
                self._no_overlap_and_eye_distance(overlap=even is None)
            finally:
                model.EVEN_ANGLE = saved

    def _no_overlap_and_eye_distance(self, overlap):
        for seed, is_3d, persist in [(s, d, k) for s in range(4) for d in (False, True) for k in ("", "section")]:
            p, b = make(seed=seed, is_3d=is_3d, n_lines=16, gap=3.0, sec_len=24.0, persist=persist)
            em = {n.id: n.scale[0] for n in b.nodes if n.kind == "glyph"}
            parent = {n.id: n.parent for n in b.nodes}
            shrink = {x.node: x for x in b.tracks if x.prop == "scale" and x.node.startswith("line")
                      and "_g" not in x.node}                    # kept lines shrinking as they move aside
            for t in np.arange(0, b.duration, 0.2):
                pos = bake.world_positions(b, t)
                size = {a: em[a] * (np.interp(t, shrink[parent[a]].times, shrink[parent[a]].values[:, 0])
                                    if parent[a] in shrink else 1.0) for a in pos}
                ids = list(pos)
                for k, a in enumerate(ids):
                    d = np.linalg.norm(pos[a] - np.array([0, 0, 1.5]))
                    self.assertGreaterEqual(d, model.MIN_EYE_DISTANCE - 1e-6, (seed, a, t))
                    for c in ids[k + 1:] if overlap else ():
                        if a.split("_")[0] == c.split("_")[0]:
                            continue                    # same line
                        gap = np.linalg.norm(pos[a] - pos[c])
                        self.assertGreater(gap, 0.45 * (size[a] + size[c]), (seed, is_3d, a, c, round(t, 2)))

    def test_even_letter_size(self):
        # every layout's biggest letter is model.EVEN_ANGLE from the eye, whatever its own size ("Approaching"
        # keeps its own: huge far away, passing by); emphasis does not change it
        eye = np.array([0.0, 0.0, model.EYE_HEIGHT])
        for text in ("太陽が", "太陽がよんでる"):
            for lp in registry.parts("layout"):
                if not lp.fits(len(text)) or lp.own_size:
                    continue
                for emph in (False, True):
                    dist = lp.fixed_distance or "mid"
                    ctx = registry.LayoutCtx(text=text, adv=[1.0] * len(text), vadv=[1.0] * len(text),
                                             em=model.text_em(dist, emph), distance=model.DISTANCE[dist], eye=1.5,
                                             is_3d=True, depth=0.15, chunks=lyrics.chunk_text(text),
                                             char_times=[0.05 * i for i in range(len(text))], anchor=(0.0, 0.0),
                                             span=(0.0, 4.0))
                    params = lp.plan(Rng(5), ctx)
                    pl = registry.even_size(lp, lp.place(ctx, params), params, eye, model.EVEN_ANGLE)
                    rot = np.broadcast_to(pl.rot, (len(pl.glyphs), 4))
                    world = pl.loc + xform.rotate(rot, np.array([g.loc for g in pl.glyphs]))
                    biggest = max(math.degrees(2 * math.atan(pl.em * g.size / 2 / np.linalg.norm(w - eye)))
                                  for g, w in zip(pl.glyphs, world))
                    self.assertAlmostEqual(biggest, model.EVEN_ANGLE, delta=0.6, msg=(lp.key, text, emph))

    def test_decimation_tolerance(self):
        times = np.linspace(0, 4, 121)
        values = np.stack([np.sin(times * 3), np.cos(times * 2), times ** 2 * 0.01], axis=1)
        idx = bake.rdp(times, values, 0.001)
        self.assertLess(len(idx), len(times))
        for c in range(3):
            approx = np.interp(times, times[idx], values[idx, c])
            self.assertLessEqual(np.abs(approx - values[:, c]).max(), 0.001 + 1e-12)

    def test_tracks_are_sane(self):
        p, b = make(n_lines=8)
        glyphs = [n for n in b.nodes if n.kind == "glyph"]
        self.assertEqual(len(glyphs), sum(len(ln.text.replace(" ", "")) for ln in p.lines))
        for tr in b.tracks:
            self.assertTrue(np.all(np.diff(tr.times) >= 0), tr.node)
            self.assertTrue(np.isfinite(tr.values).all(), tr.node)
        # emphasised characters get the accent colour
        line = next(ln for ln in p.lines if "透明" in ln.text)
        want = tuple(line.colors["accent"])
        accent = [n for n in glyphs if n.parent == f"line{line.index:03d}" and np.allclose(n.color[:3], want)]
        self.assertEqual(len(accent), 2)

    def test_speed_four_minutes(self):
        t = time.perf_counter()
        make(n_lines=60, gap=4.0)
        self.assertLess(time.perf_counter() - t, 10.0)


if __name__ == "__main__":
    unittest.main()


class TestTitle(unittest.TestCase):
    """[ti:] in the lyrics: a title card in the heading font until just before the first line (JIZURA's plan())."""

    def plan(self, first=2.0, title="夜明けのうた", artist=""):
        lines = inputs(4)
        for ln in lines:
            ln.start += first - 2.0
            ln.char_times = [t + first - 2.0 for t in ln.char_times]
        duration = lines[-1].end + 2.0
        return planner.plan(lines, sections_for(duration), duration, 7, bpm=120,
                            settings=model.Settings(title=title, artist=artist))

    def test_title_card(self):
        p = self.plan()
        t = p.title
        self.assertIsNotNone(t)
        self.assertEqual((t.text, t.index, t.font_role, t.layout, t.hold), ("夜明けのうた", -1, "display", "front", "still"))
        self.assertAlmostEqual(t.start, planner.TITLE_START)
        self.assertAlmostEqual(t.end, p.lines[0].start - planner.TITLE_GAP)
        self.assertIn(t.enter, planner.TITLE_ENTERS)
        self.assertIn(t.exit, planner.TITLE_EXITS)
        self.assertNotIn(-1, [ln.index for ln in p.lines])            # not a lyric line (gimmicks, guides, UI)
        b = bake.bake(p, metrics)
        glyphs = [n for n in b.nodes if n.parent == "title" and n.kind == "glyph" and not bake.is_band_copy(n.id)]
        self.assertEqual(len(glyphs), len("夜明けのうた"))
        self.assertTrue(all("|display|" in n.mesh for n in glyphs))
        on = {t.node: t for t in b.tracks if t.prop == "active"}[glyphs[0].id]
        self.assertLessEqual(float(on.times[-1]), p.lines[0].start)    # gone before the first line
        # the trial view of a later line leaves the title out
        self.assertIsNone(planner.subset(p, 10.0, 14.0, 2).title)
        self.assertIsNotNone(planner.subset(p, 0.0, 4.0, 0).title)

    def test_artist(self):
        self.assertIsNone(self.plan().artist)
        p = self.plan(artist="Sample Singer")
        t, a = p.title, p.artist
        self.assertEqual((a.text, a.index, a.font_role, a.enter, a.exit, a.end), ("Sample Singer", -2, "body", "fade", "fade",
                                                                                  t.end))
        self.assertAlmostEqual(a.start, t.start + planner.ARTIST_DELAY)
        self.assertLess(a.size, 1.0)
        b = bake.bake(p, metrics)
        by = {n.id: n for n in b.nodes}
        letters = lambda g: [n for n in b.nodes if n.parent == g and n.kind == "glyph" and not bake.is_band_copy(n.id)]
        art, tit = letters("artist"), letters("title")
        self.assertEqual(len(art), len("SampleSinger"))
        # below the title, smaller
        self.assertLess(by["artist"].loc[2], by["title"].loc[2] - 0.3)
        gap = lambda ns: abs(ns[1].loc[0] - ns[0].loc[0])
        self.assertLess(gap(art), gap(tit))
        self.assertIsNone(self.plan(title="", artist="Sample Singer").artist)      # only with a title (JIZURA)

    def test_no_title(self):
        self.assertIsNone(self.plan(title="").title)
        self.assertIsNone(self.plan(first=1.0).title)                   # no room before the first line
        # the title does not change the lines
        a, b = self.plan(title=""), self.plan()
        self.assertEqual([(x.layout, x.enter, x.hold, x.exit) for x in a.lines],
                         [(x.layout, x.enter, x.hold, x.exit) for x in b.lines])
